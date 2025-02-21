import json
import openai
import PyPDF2
import os
import concurrent.futures
import openai.error
import time
import random
import re
from dotenv import load_dotenv

# ReportLab imports for PDF output
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib import colors

# API Setup
load_dotenv('/Users/bereketdaniel/Desktop/Research/local_run/healthLitPro/notes.env')
api_key = os.getenv("API_KEY")
openai.api_key = api_key

def pdf_extractor(pdf_path):
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
    return text

# Load training materials and sample conversations
trainingMaterials = pdf_extractor('/Users/bereketdaniel/Desktop/Research/local_run/healthLitPro/HospitalProjectFeedbackTrainingMaterials2.pdf')
sampleConversations = pdf_extractor('/Users/bereketdaniel/Desktop/Research/local_run/healthLitPro/sampleHCPtoPatientConversations.pdf')

# Predefined parameter lists (not used in variant generation but retained for context)
jargon_use = (
    ["only uses medical jargon when completely necessary"] * 4 +
    ["sometimes uses medical jargon even when not completely necessary"] * 4 +
    ["often unnecessarily uses medical jargon"] * 2
)

clear_points = (
    ["presents the instructions/information in less than 5 points which are completely clear, identifiable, separable, and easy to follow"] * 4 +
    ["presents the instructions/information in exactly 5 clear, identifiable, and separable points"] * 4 +
    ["presents the instructions/information in more than 5 points which may or may not be clear, identifiable, or separable"] * 2
)

surgicalProcedure_list = [
    "undescended testicles", "hernia repair", "ear tube placement", "liver transplant",
    "kindey transplant", "heart transplant", "correction of bone fractures",
    "removal of skin lesions", "biopsies", "antegrade colonic enema", "central venous port",
    "catheter placement", "circumcision"
]

def generate_variant_conversation(variant, surgicalProcedure, sampleConversations):
    # Set parameters based on variant quality
    if variant == "Great":
        tone = ("professional, empathetic, informative; teach-back questions encourage understanding "
                "and optimize compliance while maintaining a positive environment. For example: "
                "'Just to ensure I explained everything well, could you tell me...?' or "
                "'Could you show me how you’ll handle the bandages, just so I know you were clear enough?'")
        points = "presents the instructions/information in exactly 5 clear, identifiable, and separable points"
        jargon = "only uses medical jargon when completely necessary"
        knowledgeCheck = "the nurse asks one question, which is answered correctly by the parent."
    elif variant == "Medium":
        tone = ("semi-professional, neutral; teach-back questions avoid discomfort but aren’t optimized for "
                "maximum understanding and compliance. For example: 'Would you mind briefly explaining that "
                "last point I made so that I don't jump too far ahead as we discuss?' or "
                "'Just to confirm that we're on the same page, what would we do if...?'")
        points = "presents the instructions/information in less than 5 points which are completely clear, identifiable, separable, and easy to follow"
        jargon = "sometimes uses medical jargon even when not completely necessary"
        knowledgeCheck = "the nurse asks two questions; the first is answered incorrectly, the second correctly."
    elif variant == "Bad":
        tone = ("unprofessional, somewhat disrespectful, rushed; teach-back questions cause discomfort or shame. For example: "
                "'You understood all that, right?' or 'Repeat what I just said so I know you understand.'")
        points = "presents the instructions/information in more than 5 points which may or may not be clear, identifiable, or separable"
        jargon = "often unnecessarily uses medical jargon"
        knowledgeCheck = "the nurse asks three questions; the first two are answered incorrectly, the last correctly."
    else:
        tone = "professional"
        points = random.choice(clear_points)
        jargon = random.choice(jargon_use)
        knowledgeCheck = "the nurse asks one question, which is answered correctly by the parent."

    # Build prompt with direct references and explicit speaker labels
    conversation_prompt = (
        f"Generate a single conversation between a Nurse and the patient's parent with the following specifications:\n"
        f"- Surgical Procedure: {surgicalProcedure}\n"
        f"- Questions: {knowledgeCheck}\n"
        f"- Tone: {tone}\n"
        f"- Jargon: The nurse {jargon}\n"
        f"- Points: The nurse {points}\n"
        f"- The conversation should be as long as possible. Typically, nurses present most of the information "
        f"in a single overview before moving into teach-back questions, answering patient questions, and similar interactions. "
        f"They follow a well-practiced script.\n"
        f"Please strictly follow the provided parameters and training materials.\n"
        f"Training Materials: {trainingMaterials}\n"
        f"Ensure the conversation is natural and conversational, without meta commentary.\n"
        f"Format the conversation with explicit speaker labels: each line should begin with 'Nurse:' or 'Parent:'.\n"
        f"These transcripts should resemble the following real conversations:\n{sampleConversations}"
    )
    
    messages = [
        {
            "role": "system",
            "content": "You are a nurse to Patient Representative (parent of the pediatric patient) conversation generator."
        },
        {
            "role": "user",
            "content": conversation_prompt
        }
    ]
    
    attempt = 0
    while attempt < 3:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=1500
            )
            conversation_text = response['choices'][0]['message']['content']
            return {
                "variant": variant,
                "surgicalProcedure": surgicalProcedure,
                "knowledgeCheck": knowledgeCheck,
                "tone": tone,
                "jargon": jargon,
                "points": points,
                "conversation": conversation_text
            }
        except openai.error.OpenAIError as e:
            time.sleep(2 ** attempt)
            attempt += 1
    return None

def get_next_variant_pdf_filename(variant):
    date_str = time.strftime("%m-%d-%Y")
    pattern = re.compile(rf"^variantTranscript_\d{{2}}-\d{{2}}-\d{{4}}_(\d+)-.*\.pdf$")
    max_id = 0
    for file in os.listdir('.'):
        m = pattern.match(file)
        if m:
            file_id = int(m.group(1))
            if file_id > max_id:
                max_id = file_id
    next_id = max_id + 1
    return f"variantTranscript_{date_str}_{next_id}-{variant}.pdf"

def write_to_pdf_single(data, pdf_path):
    doc = SimpleDocTemplate(pdf_path, pagesize=LETTER)
    story = []
    
    title_style = ParagraphStyle(
        name='title_style',
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=colors.black,
        alignment=TA_LEFT
    )
    bold_style = ParagraphStyle(
        name='bold_style',
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.black,
        alignment=TA_LEFT
    )
    italic_style = ParagraphStyle(
        name='italic_style',
        fontName='Helvetica-Oblique',
        fontSize=10,
        textColor=colors.black,
        alignment=TA_LEFT
    )
    normal_style = ParagraphStyle(
        name='normal_style',
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.black,
        alignment=TA_LEFT,
        leading=14
    )
    
    # Transcript header
    story.append(Paragraph("Transcript:", title_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Parameters
    story.append(Paragraph("<b>Parameters</b>", bold_style))
    story.append(Paragraph(f"Variant: {data['variant']}", normal_style))
    story.append(Paragraph(f"Surgical Procedure: {data['surgicalProcedure']}", normal_style))
    story.append(Paragraph(f"Knowledge Check: {data['knowledgeCheck']}", normal_style))
    story.append(Paragraph(f"Tone: {data['tone']}", normal_style))
    story.append(Paragraph(f"Jargon: {data['jargon']}", normal_style))
    story.append(Paragraph(f"Points: {data['points']}", normal_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Transcript content
    story.append(Paragraph("Transcript:", italic_style))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(data['conversation'].replace('\n', '<br/>'), normal_style))
    story.append(Spacer(1, 0.2 * inch))
    
    doc.build(story)

def process_transcripts():
    start_time = time.time()
    variants = ["Great", "Medium", "Bad"]
    data_list = []
    
    # Choose a common surgical procedure for all variants
    commonProcedure = random.choice(surgicalProcedure_list)
    
    # Generate transcripts for each variant concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_variant = {
            executor.submit(generate_variant_conversation, variant, commonProcedure, sampleConversations): variant
            for variant in variants
        }
        for future in concurrent.futures.as_completed(future_to_variant):
            try:
                data = future.result()
                if data:
                    data_list.append(data)
            except Exception as exc:
                print(f"Exception for variant {future_to_variant[future]}: {exc}")
    
    # Write each variant to its own PDF with proper naming
    for data in data_list:
        pdf_filename = get_next_variant_pdf_filename(data['variant'])
        write_to_pdf_single(data, pdf_filename)
        print(f"Transcript written to {pdf_filename}")
    
    end_time = time.time()
    print(f"Time taken: {end_time - start_time} seconds")

process_transcripts()
