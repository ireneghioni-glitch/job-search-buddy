# Projects — Irene Ghioni

## UV-Curing Predictor: ML Pipeline for Photoinitiator Screening
**Context:** Specialization project, BeCode (AI & Data Science bootcamp)
**Period:** 2026 (in progress)
**Objective:** Accelerate UV photoinitiator screening by predicting UV-curing conversion directly from molecular structure, reducing the number of lab experiments needed.

**What I did:**
- Built an end-to-end ML pipeline to predict UV-curing conversion from molecular structure
- Combined RDKit + MobileNetV2 embeddings + XGBoost
- Designed a synthetic 520k-row full factorial DoE with chemically reasonable assumptions
- Reduced embeddings from 2,560 dimensions to 64 components via PCA (-98.7% memory) without variance loss
- Developed a working web app with Reflex (lazy singleton model loading, <1s warm inference)
- Implemented SQLModel audit logging for every prediction

**Results:**
- **R² = 0.986, MAE = 1.15%** on 78k test samples
- Tool running locally as a web app
- I will present the project at **ChemAI Amsterdam (November 2026)**

**Technologies:** Python, RDKit, MobileNetV2, XGBoost, PCA, Reflex, SQLModel
**Link:** github.com/ireneghioni-glitch/AI-Powered-UV-Curing-Predictor-and-PI-Discovery

**Why it matters:** It's not an academic exercise. It stems from a real problem I experienced in the lab: every screening experiment costs time and resources. The value is not only in the model, but in the pipeline, in data quality, and in the ability to translate a chemical problem into a computational one.

---

## Predictive Formulation Tool (Excel)
**Context:** SICPA Italia Spa, R&D
**Period:** 2024
**Objective:** Accelerate formulation optimization based on rheological data.

**What I did:**
- Designed and built a predictive Excel-based tool using rheological data
- Enabled data-informed decisions on formulation parameters

**Results:**
- **40-50% reduction in formulation screening time**
- Adopted by the R&D team for daily decisions

**Technologies:** Advanced Excel, rheological data analysis

**Why it matters:** It was my first concrete approach to data-driven decision making in R&D. It showed me how much value can be unlocked even with simple tools, if used with method.

---

## Internal Analytical Request Management Software
**Context:** IGM Resins, analytical laboratory
**Period:** 2025

**What I did:**
- Built an internal software to streamline the management of analytical requests and results reporting for the analytical lab

**Why it matters:** It stems from a real operational need of the team. It taught me to translate a laboratory process into a digital workflow.

---

## Internal ML Initiative for Photoinitiator Reactivity Prediction
**Context:** IGM Resins
**Period:** 2025

**What I did:**
- Initiated an internal ML initiative to predict the reactivity of potential UV photoinitiators from internal data
- Built chemical datasets with RDKit and Mordred
- Designed exploratory models for property prediction

**Outcome:**
- Project stopped due to a change in company priorities
- It laid the foundations for a data-driven culture in the team and strengthened my motivation to complete the transition to data science

**Why it matters:** It's the moment I understood I wanted to do this as a job, not just out of curiosity. It pushed me to enroll at BeCode.