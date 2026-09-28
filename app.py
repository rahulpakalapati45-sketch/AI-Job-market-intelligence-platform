
import streamlit as st
import pandas as pd
import re
from pypdf import PdfReader
from google import genai


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Job Market Intelligence",
    page_icon="📊",
    layout="wide"
)


# ============================================================
# TITLE
# ============================================================

st.title("📊 AI-Powered Job Market Intelligence Platform")

st.write(
    "Analyze your resume against real job-market data and "
    "identify skills to improve for your target role."
)


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data
def load_data():

    jobs = pd.read_csv(
        "/content/processed_data/jobs.csv"
    )

    skills = pd.read_csv(
        "/content/processed_data/skills.csv"
    )

    job_skills = pd.read_csv(
        "/content/processed_data/job_skills.csv"
    )

    return jobs, skills, job_skills


try:

    jobs, skills, job_skills = load_data()

except Exception as e:

    st.error(
        "Could not load the project datasets. "
        "Make sure the PowerBI_Job_Market_Data files "
        "are available in /content/processed_data/"
    )

    st.stop()


# ============================================================
# ROLE GENERIC TERMS
# ============================================================

ROLE_GENERIC_TERMS = {
    "data",
    "analysis",
    "analytical",
    "analytics",
    "data analyst",
    "data analytics",
    "business",
    "management",
    "sales",
    "customer",
    "development",
    "developer",
    "work",
    "working",
    "experience",
    "skills",
    "skill",
    "project",
    "projects",
    "delivery",
    "dashboard",
    "dashboards",
    "bi"
}


# ============================================================
# GET ROLE SKILLS
# ============================================================

def get_role_skills(target_role, top_n=100):

    role_jobs = jobs[
        jobs["job_title"]
        .astype(str)
        .str.contains(
            target_role,
            case=False,
            na=False
        )
    ]

    if role_jobs.empty:
        return pd.DataFrame(
            columns=[
                "skill_name",
                "job_count",
                "demand_percentage"
            ]
        )

    role_job_ids = set(
        role_jobs["job_id"]
    )

    role_job_skills = job_skills[
        job_skills["job_id"].isin(role_job_ids)
    ]

    skill_counts = (
        role_job_skills
        .groupby("skill_id")
        .size()
        .reset_index(name="job_count")
    )

    skill_counts = skill_counts.merge(
        skills[
            ["skill_id", "skill_name"]
        ],
        on="skill_id",
        how="left"
    )

    total_jobs = len(role_job_ids)

    skill_counts["demand_percentage"] = (
        skill_counts["job_count"]
        / total_jobs
        * 100
    )

    return (
        skill_counts
        .sort_values(
            "job_count",
            ascending=False
        )
        .head(top_n)
        .reset_index(drop=True)
    )


# ============================================================
# CLEAN ROLE SKILLS
# ============================================================

def get_clean_role_skills(target_role, top_n=20):

    role_skills = get_role_skills(
        target_role,
        top_n=100
    ).copy()

    if role_skills.empty:
        return role_skills

    role_skills = role_skills[
        ~role_skills["skill_name"]
        .astype(str)
        .str.lower()
        .isin(ROLE_GENERIC_TERMS)
    ].copy()

    return (
        role_skills
        .sort_values(
            "job_count",
            ascending=False
        )
        .head(top_n)
        .reset_index(drop=True)
    )


# ============================================================
# EXTRACT RESUME TEXT
# ============================================================

def extract_resume_text(uploaded_file):

    reader = PdfReader(uploaded_file)

    text = ""

    for page in reader.pages:

        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text


# ============================================================
# RESUME SKILL EXTRACTION
# ============================================================

def extract_resume_skills(resume_text):

    text = resume_text.lower()

    skill_patterns = {

        "python": [
            "python"
        ],

        "sql": [
            "sql",
            "structured query language"
        ],

        "power bi": [
            "power bi",
            "powerbi"
        ],

        "excel": [
            "microsoft excel",
            "ms excel",
            "excel"
        ],

        "data analysis": [
            "data analysis",
            "data analytics",
            "data analyst"
        ],

        "data visualization": [
            "data visualization",
            "data visualisation"
        ],

        "tableau": [
            "tableau"
        ],

        "machine learning": [
            "machine learning",
            "machine-learning"
        ],

        "data mining": [
            "data mining"
        ],

        "etl": [
            "etl",
            "extract transform load"
        ],

        "data modeling": [
            "data modeling",
            "data modelling"
        ],

        "data warehousing": [
            "data warehousing",
            "data warehouse"
        ],

        "business intelligence": [
            "business intelligence"
        ],

        "sas": [
            "sas programming",
            "sas"
        ],

        "macros": [
            "excel macros",
            "macros"
        ]
    }

    found_skills = []

    for skill, patterns in skill_patterns.items():

        for pattern in patterns:

            if pattern in text:

                found_skills.append(skill)

                break

    return found_skills


# ============================================================
# SKILL GAP ANALYSIS
# ============================================================

def analyze_skill_gap(
    resume_skills,
    target_role
):

    required_skills = get_clean_role_skills(
        target_role,
        top_n=20
    ).copy()

    if required_skills.empty:
        return None

    resume_skill_set = set(
        skill.lower().strip()
        for skill in resume_skills
    )

    required_skills["normalized_skill"] = (
        required_skills["skill_name"]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    required_skills["status"] = (
        required_skills["normalized_skill"]
        .apply(
            lambda x:
            "Matched"
            if x in resume_skill_set
            else "Missing"
        )
    )

    matched = required_skills[
        required_skills["status"] == "Matched"
    ].copy()

    missing = required_skills[
        required_skills["status"] == "Missing"
    ].copy()

    total_demand = (
        required_skills["job_count"]
        .sum()
    )

    matched_demand = (
        matched["job_count"]
        .sum()
    )

    match_percentage = (
        matched_demand
        / total_demand
        * 100
        if total_demand > 0
        else 0
    )

    return {
        "required": required_skills,
        "matched": matched,
        "missing": missing,
        "match_percentage": match_percentage
    }


# ============================================================
# GEMINI ANALYSIS
# ============================================================

def generate_gemini_analysis(
    api_key,
    target_role,
    resume_skills,
    analysis
):

    recommendations = (
        analysis["missing"]
        .sort_values(
            "demand_percentage",
            ascending=False
        )
        .head(10)
        .copy()
    )

    recommendations["priority"] = (
        recommendations[
            "demand_percentage"
        ]
        .apply(
            lambda x:
            "High"
            if x >= 10
            else "Medium"
            if x >= 5
            else "Low"
        )
    )

    market_data = recommendations[
        [
            "skill_name",
            "demand_percentage",
            "job_count",
            "priority"
        ]
    ].to_string(
        index=False
    )

    matched = ", ".join(
        analysis["matched"][
            "skill_name"
        ].tolist()
    )

    missing = ", ".join(
        analysis["missing"][
            "skill_name"
        ].tolist()
    )

    prompt = f"""
You are an AI career recommendation engine inside an
AI-Powered Job Market Intelligence Platform.

Target role:
{target_role}

Market-weighted skill match:
{analysis["match_percentage"]:.2f}%

Resume skills:
{", ".join(resume_skills)}

Matched market skills:
{matched}

Missing market skills:
{missing}

Top market-based recommendations:
{market_data}

Provide exactly these sections:

1. OVERALL PROFILE
2. MATCHED SKILLS
3. SKILL GAPS
4. WHY THESE SKILLS MATTER
5. PRIORITIZED LEARNING ROADMAP
6. PROJECT IDEAS
7. FINAL ACTION PLAN

Rules:
- Use the supplied market data.
- Do not invent statistics.
- Mention market percentages only when supplied.
- Do not recommend skills already matched.
- Keep recommendations practical for a student/job seeker.
"""

    client = genai.Client(
        api_key=api_key
    )

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )

    return response.text


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Analysis Settings")

target_role = st.sidebar.selectbox(
    "Select Target Role",
    [
        "data analyst",
        "data engineer",
        "software engineer",
        "business analyst"
    ]
)

gemini_api_key = st.sidebar.text_input(
    "Gemini API Key",
    type="password"
)

st.sidebar.info(
    "Your API key is used only for the Gemini request."
)


# ============================================================
# RESUME UPLOAD
# ============================================================

st.header("📄 Resume Analysis")

uploaded_file = st.file_uploader(
    "Upload your resume PDF",
    type=["pdf"]
)


if uploaded_file:

    resume_text = extract_resume_text(
        uploaded_file
    )

    resume_skills = extract_resume_skills(
        resume_text
    )

    st.success(
        f"Resume loaded successfully — "
        f"{len(resume_text):,} characters extracted."
    )

    st.subheader("Detected Resume Skills")

    if resume_skills:

        skill_cols = st.columns(
            min(len(resume_skills), 4)
        )

        for i, skill in enumerate(
            resume_skills
        ):

            skill_cols[
                i % len(skill_cols)
            ].success(
                skill.title()
            )

    else:

        st.warning(
            "No supported skills were detected."
        )


    # ========================================================
    # ANALYZE BUTTON
    # ========================================================

    if st.button(
        "🔍 Analyze Resume",
        type="primary"
    ):

        analysis = analyze_skill_gap(
            resume_skills,
            target_role
        )

        if analysis is None:

            st.error(
                "No job-market data was found "
                "for this role."
            )

            st.stop()


        # ====================================================
        # KPI SECTION
        # ====================================================

        st.header("📊 Skill Gap Summary")

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Market-Weighted Skill Match",
            f'{analysis["match_percentage"]:.2f}%'
        )

        col2.metric(
            "Matched Skills",
            len(analysis["matched"])
        )

        col3.metric(
            "Missing Skills",
            len(analysis["missing"])
        )


        # ====================================================
        # MATCHED SKILLS
        # ====================================================

        st.subheader("✅ Matched Skills")

        if not analysis["matched"].empty:

            st.dataframe(
                analysis["matched"][
                    [
                        "skill_name",
                        "job_count",
                        "demand_percentage"
                    ]
                ],
                use_container_width=True
            )

        else:

            st.info(
                "No market skills matched."
            )


        # ====================================================
        # MISSING SKILLS
        # ====================================================

        st.subheader("⚠️ Missing Skills")

        st.dataframe(
            analysis["missing"][
                [
                    "skill_name",
                    "job_count",
                    "demand_percentage"
                ]
            ].head(15),
            use_container_width=True
        )


        # ====================================================
        # RECOMMENDATIONS
        # ====================================================

        st.subheader(
            "🎯 Market-Based Recommendations"
        )

        recommendations = (
            analysis["missing"]
            .sort_values(
                "demand_percentage",
                ascending=False
            )
            .head(10)
            .copy()
        )

        recommendations["priority"] = (
            recommendations[
                "demand_percentage"
            ]
            .apply(
                lambda x:
                "High"
                if x >= 10
                else "Medium"
                if x >= 5
                else "Low"
            )
        )

        st.dataframe(
            recommendations[
                [
                    "skill_name",
                    "demand_percentage",
                    "job_count",
                    "priority"
                ]
            ],
            use_container_width=True
        )


        # ====================================================
        # GEMINI
        # ====================================================

        if gemini_api_key:

            with st.spinner(
                "Generating AI career analysis..."
            ):

                try:

                    ai_result = (
                        generate_gemini_analysis(
                            gemini_api_key,
                            target_role,
                            resume_skills,
                            analysis
                        )
                    )

                    st.header(
                        "🤖 Gemini AI Career Analysis"
                    )

                    st.markdown(
                        ai_result
                    )

                except Exception as e:

                    st.error(
                        f"Gemini request failed: {e}"
                    )

        else:

            st.info(
                "Enter your Gemini API key in the "
                "sidebar to generate AI recommendations."
            )


else:

    st.info(
        "Upload a resume PDF to begin the analysis."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "AI-Powered Job Market Intelligence Platform | "
    "Python • SQL • Power BI • Gemini AI"
)
