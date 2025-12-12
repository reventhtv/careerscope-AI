# App/UploadedResumes/App.py
# DB-DISABLED version of Resume Analyzer
# - No pymysql / DB connection attempted
# - Writes simple local CSV logs instead of DB inserts (for demo)
# - Keeps pyresparser and ai_client integration
# - Robust NLTK + spaCy handling for pyresparser
# - Unified PDF extraction (pdfminer.six preferred, pdfplumber fallback)

import os
import io
import base64
import random
import time
import datetime
import socket
import platform
import secrets as pysecrets
from pathlib import Path
from PIL import Image

# Core libs
import streamlit as st
import pandas as pd
import nltk

# ========== NLTK prep (ensure required corpora exist) ==========
NLTK_DATA_DIR = os.path.join(os.getcwd(), "nltk_data")
os.makedirs(NLTK_DATA_DIR, exist_ok=True)
if NLTK_DATA_DIR not in nltk.data.path:
    nltk.data.path.insert(0, NLTK_DATA_DIR)

_required_nltk = ["stopwords", "punkt", "averaged_perceptron_tagger"]
for pkg in _required_nltk:
    try:
        if pkg == "punkt":
            nltk.data.find(f"tokenizers/{pkg}")
        elif pkg == "averaged_perceptron_tagger":
            nltk.data.find(f"taggers/{pkg}")
        else:
            nltk.data.find(f"corpora/{pkg}")
    except LookupError:
        try:
            nltk.download(pkg, download_dir=NLTK_DATA_DIR, quiet=True)
        except Exception as e:
            print(f"Warning: NLTK download failed for {pkg}: {e}")

# ========== Try to ensure spaCy model available (best-effort) ==========
_spacy_ok = False
try:
    import spacy
    try:
        spacy.load("en_core_web_sm")
        _spacy_ok = True
    except Exception:
        # attempt programmatic download (may or may not be allowed)
        try:
            import subprocess, sys
            subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"], check=True)
            spacy.load("en_core_web_sm")
            _spacy_ok = True
        except Exception as e:
            print("spaCy model not available; pyresparser may fail without it:", e)
            _spacy_ok = False
except Exception:
    _spacy_ok = False

# ========== Optional imports (graceful) ==========
_missing = []
def _try_import(name, alias=None):
    try:
        module = __import__(name)
        if alias:
            globals()[alias] = module
        else:
            globals()[name] = module
        return module
    except Exception:
        _missing.append(name)
        globals()[alias or name] = None
        return None

_try_import("pdfplumber")
_try_import("plotly.express", "px")
_try_import("plotly.graph_objects", "go")
_try_import("streamlit_tags")

# ========== pyresparser import (after NLTK/spaCy prep) ==========
try:
    from pyresparser import ResumeParser
except Exception as e:
    ResumeParser = None
    print("pyresparser import failed:", e)

# ========== PDF extraction: prefer pdfminer.six, fallback to pdfplumber ==========
_pdfminer_available = False
pdfminer_extract_text = None
try:
    from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
    from pdfminer.converter import TextConverter
    from pdfminer.layout import LAParams
    from pdfminer.pdfpage import PDFPage

    def _pdfminer_extract_text(path_or_file):
        resource_manager = PDFResourceManager()
        fake_file_handle = io.StringIO()
        laparams = LAParams()
        converter = TextConverter(resource_manager, fake_file_handle, laparams=laparams)
        interpreter = PDFPageInterpreter(resource_manager, converter)
        if isinstance(path_or_file, str):
            fh = open(path_or_file, "rb")
            close_after = True
        else:
            fh = path_or_file
            close_after = False
        try:
            for page in PDFPage.get_pages(fh, caching=True, check_extractable=True):
                interpreter.process_page(page)
            text = fake_file_handle.getvalue()
        finally:
            converter.close()
            fake_file_handle.close()
            if close_after:
                fh.close()
        return text

    pdfminer_extract_text = _pdfminer_extract_text
    _pdfminer_available = True
except Exception:
    _pdfminer_available = False

_pdfplumber_available = False
try:
    import pdfplumber as _pdfplumber
    _pdfplumber_available = True
except Exception:
    _pdfplumber_available = False

def extract_text_from_pdf(path_or_file):
    if _pdfminer_available and pdfminer_extract_text:
        try:
            return pdfminer_extract_text(path_or_file)
        except Exception:
            pass
    if _pdfplumber_available:
        try:
            if isinstance(path_or_file, str):
                with _pdfplumber.open(path_or_file) as pdf:
                    pages = [p.extract_text() or "" for p in pdf.pages]
            else:
                with _pdfplumber.open(path_or_file) as pdf:
                    pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n".join(pages)
        except Exception:
            pass
    raise RuntimeError("No PDF extraction backend available. Install pdfminer.six or pdfplumber.")

# ========== Courses import (local) ==========
try:
    from Courses import ds_course, web_course, android_course, ios_course, uiux_course, resume_videos, interview_videos
except Exception:
    ds_course = web_course = android_course = ios_course = uiux_course = []
    resume_videos = interview_videos = []

# ========== DB-disabled logging (local CSV) ==========
LOG_DIR = Path("./data_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
USER_LOG_CSV = LOG_DIR / "user_data_log.csv"
FEEDBACK_LOG_CSV = LOG_DIR / "feedback_log.csv"

def insert_data(sec_token, ip_add, host_name, dev_user, os_name_ver, latlong, city, state, country,
                act_name, act_mail, act_mob, name, email, res_score, timestamp, no_of_pages,
                reco_field, cand_level, skills, recommended_skills, courses, pdf_name):
    # Append a single-row CSV for demo logging. No DB required.
    row = {
        "sec_token": sec_token,
        "ip_add": ip_add,
        "host_name": host_name,
        "dev_user": dev_user,
        "os_name_ver": os_name_ver,
        "latlong": latlong,
        "city": city,
        "state": state,
        "country": country,
        "act_name": act_name,
        "act_mail": act_mail,
        "act_mob": act_mob,
        "name": name,
        "email": email,
        "resume_score": res_score,
        "timestamp": timestamp,
        "no_of_pages": no_of_pages,
        "reco_field": reco_field,
        "cand_level": cand_level,
        "skills": skills,
        "recommended_skills": recommended_skills,
        "courses": courses,
        "pdf_name": pdf_name
    }
    df = pd.DataFrame([row])
    if USER_LOG_CSV.exists():
        df.to_csv(USER_LOG_CSV, mode="a", header=False, index=False)
    else:
        df.to_csv(USER_LOG_CSV, index=False)

def insertf_data(feed_name, feed_email, feed_score, comments, Timestamp):
    row = {
        "feed_name": feed_name,
        "feed_email": feed_email,
        "feed_score": feed_score,
        "comments": comments,
        "Timestamp": Timestamp
    }
    df = pd.DataFrame([row])
    if FEEDBACK_LOG_CSV.exists():
        df.to_csv(FEEDBACK_LOG_CSV, mode="a", header=False, index=False)
    else:
        df.to_csv(FEEDBACK_LOG_CSV, index=False)

# ========== Helpers ==========
def get_csv_download_link(df, filename, text):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'
    return href

def show_pdf(file_path):
    try:
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="1000" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error("Unable to preview PDF: " + str(e))

def course_recommender(course_list):
    st.subheader("**Courses & Certificates Recommendations 👨‍🎓**")
    random.shuffle(course_list)
    no_of_reco = st.slider('Choose Number of Course Recommendations:', 1, 10, 5)
    rec_course = []
    c = 0
    for c_name, c_link in course_list:
        c += 1
        st.markdown(f"({c}) [{c_name}]({c_link})")
        rec_course.append(c_name)
        if c == no_of_reco:
            break
    return rec_course

# ========== Page config ==========
st.set_page_config(page_title="AI Resume Analyzer", page_icon='./Logo/recommend.png')

# ========== Main ==========
def run():
    try:
        img = Image.open('./Logo/RESUM.png')
        st.image(img)
    except Exception:
        st.title("AI Resume Analyzer")

    st.sidebar.markdown("# Choose Something...")
    activities = ["User", "Feedback", "About", "Admin"]
    choice = st.sidebar.selectbox("Choose among the given options:", activities)
    link = '<b>Built with 🤍 by <a href="https://dnoobnerd.netlify.app/" style="text-decoration: none; color: #021659;">Deepak Padhi</a></b>'
    st.sidebar.markdown(link, unsafe_allow_html=True)

    os.makedirs("./Uploaded_Resumes", exist_ok=True)

    # ---------- USER ----------
    if choice == "User":
        act_name = st.text_input('Name*')
        act_mail = st.text_input('Mail*')
        act_mob  = st.text_input('Mobile Number*')
        sec_token = pysecrets.token_urlsafe(12)

        try:
            host_name = socket.gethostname()
        except Exception:
            host_name = "unknown"
        try:
            ip_add = socket.gethostbyname(host_name)
        except Exception:
            ip_add = ""

        try:
            dev_user = os.getlogin()
        except Exception:
            dev_user = os.environ.get("USER") or "unknown"

        os_name_ver = platform.system() + " " + platform.release()

        # geolocation (optional, best-effort)
        latlong = None
        city = state = country = ""
        try:
            if globals().get("geocoder"):
                g = geocoder.ip('me')
                latlong = g.latlng
            if globals().get("geopy") and latlong:
                geolocator = geopy.geocoders.Nominatim(user_agent="http")
                try:
                    location = geolocator.reverse(latlong, language='en')
                    address = location.raw.get('address', {})
                    city = address.get('city', '') or address.get('town', '') or address.get('village','')
                    state = address.get('state', '')
                    country = address.get('country', '')
                except Exception:
                    city = state = country = ""
        except Exception:
            latlong = None
            city = state = country = ""

        st.markdown('''<h5 style='text-align: left; color: #021659;'> Upload Your Resume, And Get Smart Recommendations</h5>''',unsafe_allow_html=True)
        pdf_file = st.file_uploader("Choose your Resume", type=["pdf"])
        if pdf_file is not None:
            with st.spinner('Hang On While We Cook Magic For You...'):
                time.sleep(1)

            save_image_path = os.path.join('./Uploaded_Resumes', pdf_file.name)
            pdf_name = pdf_file.name
            with open(save_image_path, "wb") as f:
                f.write(pdf_file.getbuffer())

            try:
                show_pdf(save_image_path)
            except Exception:
                pass
                
            try:
                resume_text = extract_text_from_pdf(save_image_path)
            except Exception as e:
                st.error("Failed to extract text from PDF: " + str(e))
                resume_text = ""
            # Save parsed/extracted text so AI suggestions can find it
            try:
            # keep a global name too (some code checks globals())
                globals()["resume_text"] = resume_text
            # also save to Streamlit session so UI picks it up
                st.session_state["resume_text"] = resume_text
            except Exception:
                pass

            resume_data = {}
            if ResumeParser:
                try:
                    parsed = ResumeParser(save_image_path).get_extracted_data()
                    resume_data = parsed or {}
                except Exception as e:
                    print("pyresparser parse error:", e)
                    resume_data = {}
            else:
                resume_data = {}

            if resume_data:
                st.header("**Resume Analysis 🤘**")
                try:
                    st.success("Hello "+ str(resume_data.get('name','')))
                    st.subheader("**Your Basic info 👀**")
                    st.text('Name: ' + str(resume_data.get('name','')))
                    st.text('Email: ' + str(resume_data.get('email','')))
                    st.text('Contact: ' + str(resume_data.get('mobile_number','')))
                    st.text('Degree: '+ str(resume_data.get('degree','')))
                    st.text('Resume pages: '+str(resume_data.get('no_of_pages','')))
                except Exception:
                    pass

                # candidate level guess
                cand_level = "Fresher"
                try:
                    no_of_pages = int(resume_data.get('no_of_pages') or 0)
                except Exception:
                    no_of_pages = 0
                if no_of_pages < 1:
                    cand_level = "NA"
                    st.markdown("<h4 style='text-align: left; color: #d73b5c;'>You are at Fresher level!</h4>", unsafe_allow_html=True)
                elif 'INTERNSHIP' in (resume_text or "").upper():
                    cand_level = "Intermediate"
                    st.markdown("<h4 style='text-align: left; color: #1ed760;'>You are at intermediate level!</h4>", unsafe_allow_html=True)
                elif 'EXPERIENCE' in (resume_text or "").upper():
                    cand_level = "Experienced"
                    st.markdown("<h4 style='text-align: left; color: #fba171;'>You are at experience level!</h4>", unsafe_allow_html=True)
                else:
                    cand_level = "Fresher"
                    st.markdown("<h4 style='text-align: left; color: #fba171;'>You are at Fresher level!!</h4>", unsafe_allow_html=True)

                # skills
                st.subheader("**Skills Recommendation 💡**")
                skills_list = resume_data.get('skills') or []
                try:
                    st_tags = globals().get("st_tags") or None
                    if st_tags:
                        st_tags(label='### Your Current Skills', text='See our skills recommendation below', value=skills_list, key='1')
                    else:
                        st.write("Skills:", ", ".join(skills_list))
                except Exception:
                    st.write("Skills:", ", ".join(skills_list))

                # keywords & recommendations (kept original logic)
                ds_keyword = ['tensorflow','keras','pytorch','machine learning','deep learning','flask','streamlit']
                web_keyword = ['react', 'django', 'node js', 'react js', 'php', 'laravel', 'magento', 'wordpress','javascript', 'angular js', 'c#', 'asp.net', 'flask']
                android_keyword = ['android','android development','flutter','kotlin','xml','kivy']
                ios_keyword = ['ios','ios development','swift','cocoa','cocoa touch','xcode']
                uiux_keyword = ['ux','adobe xd','figma','zeplin','balsamiq','ui','prototyping','wireframes','adobe photoshop','photoshop','illustrator']
                n_any = ['english','communication','writing', 'microsoft office', 'leadership','customer management', 'social media']

                recommended_skills = []
                reco_field = ''
                rec_course = ''

                for i in skills_list:
                    if i is None:
                        continue
                    il = str(i).lower()
                    if il in ds_keyword:
                        reco_field = 'Data Science'
                        st.success("** Our analysis says you are looking for Data Science Jobs.**")
                        recommended_skills = ['Data Visualization','Predictive Analysis','Statistical Modeling','Data Mining','Clustering & Classification','Data Analytics','Quantitative Analysis','Web Scraping','ML Algorithms','Keras','Pytorch','Probability','Scikit-learn','Tensorflow','Flask','Streamlit']
                        try:
                            if globals().get("st_tags"):
                                st_tags(label='### Recommended skills for you.', text='Recommended skills generated from System', value=recommended_skills, key='2')
                            else:
                                st.write("Recommended skills:", ", ".join(recommended_skills))
                        except Exception:
                            st.write("Recommended skills:", ", ".join(recommended_skills))
                        st.markdown("<h5 style='text-align: left; color: #1ed760;'>Adding these skills to resume will boost🚀 the chances of getting a Job</h5>", unsafe_allow_html=True)
                        rec_course = course_recommender(ds_course)
                        break
                    elif il in web_keyword:
                        reco_field = 'Web Development'
                        st.success("** Our analysis says you are looking for Web Development Jobs **")
                        recommended_skills = ['React','Django','Node JS','React JS','PHP','Laravel','Magento','Wordpress','Javascript','Angular JS','C#','Flask','SDK']
                        try:
                            if globals().get("st_tags"):
                                st_tags(label='### Recommended skills for you.', text='Recommended skills generated from System', value=recommended_skills, key='3')
                            else:
                                st.write("Recommended skills:", ", ".join(recommended_skills))
                        except Exception:
                            st.write("Recommended skills:", ", ".join(recommended_skills))
                        st.markdown("<h5 style='text-align: left; color: #1ed760;'>Adding these skills to resume will boost🚀 the chances of getting a Job💼</h5>", unsafe_allow_html=True)
                        rec_course = course_recommender(web_course)
                        break
                    elif il in android_keyword:
                        reco_field = 'Android Development'
                        st.success("** Our analysis says you are looking for Android App Development Jobs **")
                        recommended_skills = ['Android','Android development','Flutter','Kotlin','XML','Java','Kivy','GIT','SDK','SQLite']
                        try:
                            if globals().get("st_tags"):
                                st_tags(label='### Recommended skills for you.', text='Recommended skills generated from System', value=recommended_skills, key='4')
                            else:
                                st.write("Recommended skills:", ", ".join(recommended_skills))
                        except Exception:
                            st.write("Recommended skills:", ", ".join(recommended_skills))
                        st.markdown("<h5 style='text-align: left; color: #1ed760;'>Adding these skills to resume will boost🚀 the chances of getting a Job💼</h5>", unsafe_allow_html=True)
                        rec_course = course_recommender(android_course)
                        break
                    elif il in ios_keyword:
                        reco_field = 'IOS Development'
                        st.success("** Our analysis says you are looking for IOS App Development Jobs **")
                        recommended_skills = ['IOS','IOS Development','Swift','Cocoa','Cocoa Touch','Xcode','Objective-C','SQLite','Plist','StoreKit','UI-Kit','AV Foundation','Auto-Layout']
                        try:
                            if globals().get("st_tags"):
                                st_tags(label='### Recommended skills for you.', text='Recommended skills generated from System', value=recommended_skills, key='5')
                            else:
                                st.write("Recommended skills:", ", ".join(recommended_skills))
                        except Exception:
                            st.write("Recommended skills:", ", ".join(recommended_skills))
                        rec_course = course_recommender(ios_course)
                        break
                    elif il in uiux_keyword:
                        reco_field = 'UI-UX Development'
                        st.success("** Our analysis says you are looking for UI-UX Development Jobs **")
                        recommended_skills = ['UI','User Experience','Adobe XD','Figma','Zeplin','Balsamiq','Prototyping','Wireframes','Storyframes','Adobe Photoshop','Editing','Illustrator','After Effects','Premier Pro','Indesign']
                        try:
                            if globals().get("st_tags"):
                                st_tags(label='### Recommended skills for you.', text='Recommended skills generated from System', value=recommended_skills, key='6')
                            else:
                                st.write("Recommended skills:", ", ".join(recommended_skills))
                        except Exception:
                            st.write("Recommended skills:", ", ".join(recommended_skills))
                        rec_course = course_recommender(uiux_course)
                        break
                    elif il in n_any:
                        reco_field = 'NA'
                        st.warning("** Currently our tool only predicts and recommends for Data Science, Web, Android, IOS and UI/UX Development**")
                        recommended_skills = ['No Recommendations']
                        try:
                            if globals().get("st_tags"):
                                st_tags(label='### Recommended skills for you.', text='Currently No Recommendations', value=recommended_skills, key='7')
                            else:
                                st.write("No recommendations available")
                        except Exception:
                            st.write("No recommendations available")
                        rec_course = "Sorry! Not Available for this Field"
                        break

                # Resume scoring (simplified)
                st.subheader("**Resume Tips & Ideas 🥂**")
                resume_score = 0
                text_upper = (resume_text or "").upper()
                if "OBJECTIVE" in text_upper or "SUMMARY" in text_upper:
                    resume_score += 6
                    st.markdown("<h5 style='text-align: left; color: #1ed760;'>[+] Awesome! You have added Objective/Summary</h5>", unsafe_allow_html=True)
                if "EDUCATION" in text_upper or "SCHOOL" in text_upper or "COLLEGE" in text_upper:
                    resume_score += 12
                    st.markdown("<h5 style='text-align: left; color: #1ed760;'>[+] Awesome! You have added Education Details</h5>", unsafe_allow_html=True)
                if "EXPERIENCE" in text_upper:
                    resume_score += 16
                    st.markdown("<h5 style='text-align: left; color: #1ed760;'>[+] Awesome! You have added Experience</h5>", unsafe_allow_html=True)
                if "INTERNSHIP" in text_upper:
                    resume_score += 6
                    st.markdown("<h5 style='text-align: left; color: #1ed760;'>[+] Awesome! You have added Internships</h5>", unsafe_allow_html=True)
                if "SKILL" in text_upper:
                    resume_score += 7
                    st.markdown("<h5 style='text-align: left; color: #1ed760;'>[+] Awesome! You have added Skills</h5>", unsafe_allow_html=True)
                if "PROJECT" in text_upper:
                    resume_score += 19
                    st.markdown("<h5 style='text-align: left; color: #1ed760;'>[+] Awesome! You have added your Projects</h5>", unsafe_allow_html=True)

                st.subheader("**Resume Score 📝**")
                my_bar = st.progress(0)
                for percent_complete in range(min(resume_score, 100)):
                    time.sleep(0.01)
                    my_bar.progress(percent_complete + 1)
                st.success(f'** Your Resume Writing Score: {resume_score} **')
                st.warning("** Note: This score is calculated based on the content that you have in your Resume. **")

                # Timestamp & local log
                ts = time.time()
                cur_date = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                cur_time = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                timestamp = str(cur_date + '_' + cur_time)

                # log to local CSV (DB-disabled)
                insert_data(str(sec_token), str(ip_add), host_name, dev_user, os_name_ver, latlong, city, state, country,
                            act_name, act_mail, act_mob, resume_data.get('name',''), resume_data.get('email',''),
                            str(resume_score), timestamp, str(resume_data.get('no_of_pages','')), reco_field, cand_level,
                            str(resume_data.get('skills','')), str(recommended_skills), str(rec_course), pdf_name)

                # Bonus videos
                try:
                    st.header("**Bonus Video for Resume Writing Tips💡**")
                    resume_vid = random.choice(resume_videos) if resume_videos else None
                    if resume_vid:
                        st.video(resume_vid)
                except Exception:
                    pass

                try:
                    st.header("**Bonus Video for Interview Tips💡**")
                    interview_vid = random.choice(interview_videos) if interview_videos else None
                    if interview_vid:
                        st.video(interview_vid)
                except Exception:
                    pass

                st.balloons()
            else:
                st.error('Something went wrong while parsing resume. Try pasting resume text into AI suggestions if parsing fails.')

    # ---------- FEEDBACK ----------
    elif choice == "Feedback":
        ts = time.time()
        cur_date = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        cur_time = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        timestamp = str(cur_date+'_'+cur_time)

        with st.form("my_form"):
            st.write("Feedback form")
            feed_name = st.text_input('Name')
            feed_email = st.text_input('Email')
            feed_score = st.slider('Rate Us From 1 - 5', 1, 5)
            comments = st.text_input('Comments')
            Timestamp = timestamp
            submitted = st.form_submit_button("Submit")
            if submitted:
                insertf_data(feed_name, feed_email, feed_score, comments, Timestamp)
                st.success("Thanks! Your Feedback was recorded.")
                st.balloons()

        # show feedback log if exists
        if FEEDBACK_LOG_CSV.exists():
            try:
                df = pd.read_csv(FEEDBACK_LOG_CSV)
                st.subheader("**Past User Rating's**")
                if 'feed_score' in df.columns and px:
                    labels = df.feed_score.unique()
                    values = df.feed_score.value_counts()
                    fig = px.pie(values=values, names=labels, title="Chart of User Rating Score From 1 - 5", color_discrete_sequence=px.colors.sequential.Aggrnyl)
                    st.plotly_chart(fig)
                st.subheader("**User Comment's**")
                st.dataframe(df[['feed_name', 'comments']] if set(['feed_name','comments']).issubset(df.columns) else df)
            except Exception as e:
                st.write("Unable to read feedback log:", e)
        else:
            st.info("No feedback recorded yet.")

    # ---------- ABOUT ----------
    elif choice == "About":
        st.subheader("**About The Tool - AI RESUME ANALYZER**")
        st.markdown("""
        <p>A tool which parses information from a resume using natural language processing and finds the keywords, cluster them onto sectors based on their keywords. And lastly show recommendations, predictions, analytics to the applicant based on keyword matching.</p>
        <p><b>How to use it:</b> Upload your resume as PDF. Use Feedback to give feedback. Admin can login to view local logs when available.</p>
        <p>Built with 🤍 by <a href="https://dnoobnerd.netlify.app/">Deepak Padhi</a>.</p>
        """, unsafe_allow_html=True)

    # ---------- ADMIN ----------
    else:
        st.success('Admin Panel (DB disabled)')
        ad_user = st.text_input("Username")
        ad_password = st.text_input("Password", type='password')

        if st.button('Login'):
            if ad_user == 'admin' and ad_password == 'admin@resume-analyzer':
                # show local logs instead of DB
                if USER_LOG_CSV.exists():
                    try:
                        dff = pd.read_csv(USER_LOG_CSV)
                        st.header("**User's Data (local log)**")
                        st.dataframe(dff)
                        st.markdown(get_csv_download_link(dff, 'User_Data.csv', 'Download Report'), unsafe_allow_html=True)
                    except Exception as e:
                        st.write("Unable to read local user log:", e)
                else:
                    st.info("No user logs yet (DB was not configured).")

                if FEEDBACK_LOG_CSV.exists():
                    try:
                        dff2 = pd.read_csv(FEEDBACK_LOG_CSV)
                        st.header("**Feedback (local log)**")
                        st.dataframe(dff2)
                        st.markdown(get_csv_download_link(dff2, 'Feedback_Data.csv', 'Download Feedback Report'), unsafe_allow_html=True)
                    except Exception as e:
                        st.write("Unable to read feedback log:", e)
                else:
                    st.info("No feedback logs yet.")
            else:
                st.error("Wrong ID & Password Provided")

    # ---------- AI Suggestions ----------
    try:
        from ai_client import ask_ai
    except Exception:
        def ask_ai(prompt: str):
            return "AI suggestions not configured. Add AI_API_KEY or service account JSON to Streamlit secrets to enable."

    st.markdown("---")
    st.subheader("AI-powered Suggestions")
    _possible_keys = ["resume_text", "text", "doc_text", "parsed_text", "resume_str", "extracted_text"]
    resume_text = None

    # 1) Check globals
    for k in _possible_keys:
        if k in globals() and globals().get(k):
            resume_text = globals().get(k)
            break
    # 2) Check session_state
    if not resume_text:
        for k in _possible_keys:
            if st.session_state.get(k):
                resume_text = st.session_state.get(k)
                break
    # 3) Fallback: let user paste text
    if not resume_text:
        st.info("No parsed resume text detected. Paste resume text here to get AI suggestions.")
        resume_text = st.text_area("Paste resume text (optional)", value="", height=200)

    if st.button("Get AI suggestions"):
        with st.spinner("Generating AI suggestions..."):
            try:
                prompt = (
                    "You are an expert career coach. Analyze this resume and provide:\n"
                    "1) Top strengths\n"
                    "2) Weaknesses or missing items\n"
                    "3) Key ATS keywords to add\n"
                    "4) Improvements to professional summary\n\n"
                    f"Resume:\n{resume_text}"
                )
                ai_out = ask_ai(prompt)
                st.success("AI Suggestions")
                st.write(ai_out)
            except Exception as e:
                st.error(f"AI error: {e}")

if __name__ == "__main__":
    run()
