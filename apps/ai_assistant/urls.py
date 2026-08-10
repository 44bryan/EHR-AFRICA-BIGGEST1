from django.urls import path
from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('', views.ai_home_view, name='home'),
    path('new/', views.new_conversation_view, name='new_conversation'),
    path('<uuid:pk>/', views.conversation_view, name='conversation'),
    path('<uuid:pk>/message/', views.send_message_view, name='send_message'),
    path('<uuid:pk>/clear/', views.clear_conversation_view, name='clear'),
    # Voice EMR — stateless extraction (create page — no consultation ID)
    path('voice/extract/', views.voice_extract_view, name='voice_extract'),
    # Voice EMR — AI-first consultation (speak → AI fills → doctor approves)
    path('voice/<uuid:consultation_id>/', views.voice_transcribe_view, name='voice_transcribe'),
    path('voice/<uuid:consultation_id>/approve/', views.voice_approve_view, name='voice_approve'),
    # Virtual Receptionist
    path('receptionist/', views.virtual_receptionist_view, name='receptionist'),
    # Analytics AI
    path('analytics/', views.analytics_ai_view, name='analytics'),
    # Diagnosis Assist (inline AI panel)
    path('suggest-diagnosis/', views.suggest_diagnosis_view, name='suggest_diagnosis'),
    # Drug Interaction Checker
    path('drug-interactions/', views.drug_interaction_view, name='drug_interactions'),
    # Patient AI Risk Summary
    path('patient-risk/<str:patient_id>/', views.patient_risk_summary_view, name='patient_risk'),
    # Patient AI Chatbot
    path('patient-chat/<str:patient_id>/', views.patient_chat_view, name='patient_chat'),
    # AI Triage Scoring
    path('triage/', views.ai_triage_view, name='triage'),
    # AI Imaging / Investigation Analysis
    path('imaging-analysis/<int:result_id>/', views.ai_imaging_analysis_view, name='imaging_analysis'),
    # AI SOAP Note Generator
    path('soap-note/', views.ai_soap_note_view, name='soap_note'),
    # AI Lab Result Interpretation
    path('lab-interpret/', views.ai_lab_interpret_view, name='lab_interpret'),
    # AI Investigation Findings Template Generator
    path('investigation-template/', views.ai_investigation_template_view, name='investigation_template'),
    # AI Lab Panel Summary — combined interpretation of all results in one order
    path('lab-panel-summary/', views.ai_lab_panel_summary_view, name='lab_panel_summary'),
    # Department Stats AI Insights
    path('stats-insights/', views.stats_insights_view, name='stats_insights'),
]
