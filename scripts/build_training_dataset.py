"""
Build QLoRA training dataset from the CritiPlan pipeline.

Steps:
  1. Collect all existing project briefs (data/raw/docs/)
  2. Generate synthetic briefs across 15+ domains
  3. Run each through the rule-based pipeline (deterministic, no Ollama needed)
  4. Filter: critic score >= 0.70 AND task count 3-20
  5. Format as chat JSONL (Qwen/LLaMA instruction format)
  6. Save to data/training/

Usage:
  python scripts/build_training_dataset.py
  python scripts/build_training_dataset.py --max-synthetic 300 --min-score 0.70
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import textwrap
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.critic import CriticAgent
from src.agents.planner import PlannerAgent, RequirementItem
from src.parsers.brief_parser import BriefParser, BriefValidationError
from src.services.effort_estimator import EffortEstimator
from src.pipelines.evaluate import FallbackOnlyClient


OUTPUT_DIR = PROJECT_ROOT / "data" / "training"
BRIEFS_DIR = PROJECT_ROOT / "data" / "raw" / "docs"

# ─────────────────────────────────────────────────────────────────────────────
# Synthetic brief templates  (domain, title, features, nfr)
# Each entry produces ~3 brief variants (small / medium / large)
# ─────────────────────────────────────────────────────────────────────────────
DOMAINS: list[dict] = [
    {
        "domain": "telemedicine",
        "title": "Telemedicine Platform",
        "overview": "A web and mobile platform connecting patients with doctors for virtual consultations.",
        "features_small": [
            "Patients can register and create a health profile with medical history.",
            "Doctors can schedule and conduct video consultations.",
            "Prescriptions are generated digitally and sent to pharmacies.",
        ],
        "features_medium": [
            "Patients can register and create a health profile with medical history.",
            "Doctors can schedule and conduct video consultations.",
            "Prescriptions are generated digitally and sent to pharmacies.",
            "Appointment reminders are sent via SMS and email.",
            "Medical records are stored securely and accessible to authorized providers.",
        ],
        "features_large": [
            "Patients can register and create a health profile with medical history.",
            "Doctors can schedule and conduct video consultations.",
            "Prescriptions are generated digitally and sent to pharmacies.",
            "Appointment reminders are sent via SMS and email.",
            "Medical records are stored securely and accessible to authorized providers.",
            "Patients can request lab tests and view results online.",
            "Insurance claims are submitted automatically after each consultation.",
            "Admins can manage doctor availability and specializations.",
        ],
        "nfr": "HIPAA compliance for all PHI. 99.9% uptime. Video calls must support 720p at 30fps. API response under 500ms.",
    },
    {
        "domain": "logistics",
        "title": "Fleet & Delivery Management System",
        "overview": "A platform for managing delivery fleets, route optimization, and shipment tracking.",
        "features_small": [
            "Dispatchers can assign deliveries to available drivers.",
            "Drivers receive route instructions on a mobile app.",
            "Customers can track their shipment in real time.",
        ],
        "features_medium": [
            "Dispatchers can assign deliveries to available drivers.",
            "Drivers receive route instructions on a mobile app.",
            "Customers can track their shipment in real time.",
            "The system automatically optimizes routes to minimize fuel consumption.",
            "Delivery proof is captured via digital signature or photo.",
        ],
        "features_large": [
            "Dispatchers can assign deliveries to available drivers.",
            "Drivers receive route instructions on a mobile app.",
            "Customers can track their shipment in real time.",
            "The system automatically optimizes routes to minimize fuel consumption.",
            "Delivery proof is captured via digital signature or photo.",
            "Warehouse managers can manage stock levels and dispatch orders.",
            "Vehicle maintenance schedules are tracked and alerts are sent.",
            "Analytics dashboards show on-time delivery rates and driver performance.",
        ],
        "nfr": "GPS tracking updates every 30 seconds. Must handle 10,000 active deliveries concurrently. Data encrypted in transit and at rest.",
    },
    {
        "domain": "real_estate",
        "title": "Real Estate Listing & Management Platform",
        "overview": "An online platform for listing, searching, and managing real estate properties.",
        "features_small": [
            "Agents can list properties with photos, descriptions, and pricing.",
            "Buyers can search listings by location, price range, and type.",
            "Users can schedule property viewings online.",
        ],
        "features_medium": [
            "Agents can list properties with photos, descriptions, and pricing.",
            "Buyers can search listings by location, price range, and type.",
            "Users can schedule property viewings online.",
            "Mortgage calculators help buyers estimate monthly payments.",
            "Agents receive notifications when buyers express interest in their listings.",
        ],
        "features_large": [
            "Agents can list properties with photos, descriptions, and pricing.",
            "Buyers can search listings by location, price range, and type.",
            "Users can schedule property viewings online.",
            "Mortgage calculators help buyers estimate monthly payments.",
            "Agents receive notifications when buyers express interest in their listings.",
            "The system generates rental agreements and purchase contracts.",
            "Payment processing handles deposits and monthly rent collection.",
            "Admins approve new agent registrations and manage subscriptions.",
        ],
        "nfr": "Image storage up to 50 photos per listing. Search results returned in under 1 second. GDPR-compliant data handling.",
    },
    {
        "domain": "restaurant",
        "title": "Restaurant Management & Online Ordering System",
        "overview": "A platform for restaurant operations, online orders, and table reservations.",
        "features_small": [
            "Customers can browse the menu and place online orders.",
            "Kitchen staff receive order tickets on a display screen.",
            "Managers can update menu items and pricing.",
        ],
        "features_medium": [
            "Customers can browse the menu and place online orders.",
            "Kitchen staff receive order tickets on a display screen.",
            "Managers can update menu items and pricing.",
            "Customers can make table reservations and receive confirmation emails.",
            "Loyalty points are awarded for each order and redeemable for discounts.",
        ],
        "features_large": [
            "Customers can browse the menu and place online orders.",
            "Kitchen staff receive order tickets on a display screen.",
            "Managers can update menu items and pricing.",
            "Customers can make table reservations and receive confirmation emails.",
            "Loyalty points are awarded for each order and redeemable for discounts.",
            "Delivery drivers are assigned automatically based on proximity.",
            "Inventory levels are tracked and suppliers are notified when stock is low.",
            "Sales reports are generated daily with revenue and popular item analysis.",
        ],
        "nfr": "Order confirmation under 2 seconds. Support 500 concurrent online orders. PCI-DSS compliant payment processing.",
    },
    {
        "domain": "legal_tech",
        "title": "Legal Document Management System",
        "overview": "A platform for law firms to manage cases, contracts, and client communications.",
        "features_small": [
            "Lawyers can create and store case files with associated documents.",
            "Clients can sign contracts electronically.",
            "Deadlines and court dates are tracked with automated reminders.",
        ],
        "features_medium": [
            "Lawyers can create and store case files with associated documents.",
            "Clients can sign contracts electronically.",
            "Deadlines and court dates are tracked with automated reminders.",
            "Time tracking enables billing by the hour for each case.",
            "Document version history is maintained for all contracts.",
        ],
        "features_large": [
            "Lawyers can create and store case files with associated documents.",
            "Clients can sign contracts electronically.",
            "Deadlines and court dates are tracked with automated reminders.",
            "Time tracking enables billing by the hour for each case.",
            "Document version history is maintained for all contracts.",
            "AI-powered contract clause extraction flags unusual terms.",
            "Client portal allows secure message exchange and document sharing.",
            "Billing invoices are generated automatically based on logged hours.",
        ],
        "nfr": "Attorney-client privilege requires end-to-end encryption. SOC 2 Type II compliance. Audit trail for all document access.",
    },
    {
        "domain": "smart_home",
        "title": "Smart Home Automation Platform",
        "overview": "An IoT platform for controlling and automating home devices remotely.",
        "features_small": [
            "Users can control lights, thermostats, and locks from a mobile app.",
            "Devices report their status in real time to the dashboard.",
            "Users can create automation rules (e.g. turn off lights at 10pm).",
        ],
        "features_medium": [
            "Users can control lights, thermostats, and locks from a mobile app.",
            "Devices report their status in real time to the dashboard.",
            "Users can create automation rules (e.g. turn off lights at 10pm).",
            "Energy consumption is tracked and shown in monthly reports.",
            "Voice commands via Alexa and Google Home are supported.",
        ],
        "features_large": [
            "Users can control lights, thermostats, and locks from a mobile app.",
            "Devices report their status in real time to the dashboard.",
            "Users can create automation rules (e.g. turn off lights at 10pm).",
            "Energy consumption is tracked and shown in monthly reports.",
            "Voice commands via Alexa and Google Home are supported.",
            "Security cameras stream live video with motion-detection alerts.",
            "Multi-home management allows controlling devices in multiple properties.",
            "Device firmware is updated over-the-air with rollback capability.",
        ],
        "nfr": "Device commands execute within 200ms. Must support 10,000 devices per account. TLS 1.3 for all device communication.",
    },
    {
        "domain": "event_management",
        "title": "Event Management & Ticketing Platform",
        "overview": "A platform for organizing events, selling tickets, and managing attendees.",
        "features_small": [
            "Organizers can create events with date, venue, and ticket tiers.",
            "Attendees can purchase tickets and receive QR code confirmations.",
            "Check-in staff can scan QR codes at the venue entrance.",
        ],
        "features_medium": [
            "Organizers can create events with date, venue, and ticket tiers.",
            "Attendees can purchase tickets and receive QR code confirmations.",
            "Check-in staff can scan QR codes at the venue entrance.",
            "Waiting lists are managed automatically when tickets sell out.",
            "Organizers receive real-time sales analytics and attendee demographics.",
        ],
        "features_large": [
            "Organizers can create events with date, venue, and ticket tiers.",
            "Attendees can purchase tickets and receive QR code confirmations.",
            "Check-in staff can scan QR codes at the venue entrance.",
            "Waiting lists are managed automatically when tickets sell out.",
            "Organizers receive real-time sales analytics and attendee demographics.",
            "Sponsor packages are sold and tracked with branding placement.",
            "Attendees can submit session feedback and ratings after events.",
            "Recurring event series are managed with shared attendee history.",
        ],
        "nfr": "Handle 50,000 simultaneous ticket purchases during launches. Payment refunds processed within 5 business days. GDPR for attendee data.",
    },
    {
        "domain": "project_management",
        "title": "Team Project Management Tool",
        "overview": "A collaborative project management tool for teams to track tasks and milestones.",
        "features_small": [
            "Team members can create tasks and assign them to colleagues.",
            "Projects have milestones with target dates and progress tracking.",
            "File attachments can be added to tasks.",
        ],
        "features_medium": [
            "Team members can create tasks and assign them to colleagues.",
            "Projects have milestones with target dates and progress tracking.",
            "File attachments can be added to tasks.",
            "Kanban boards visualize task status across workflow stages.",
            "Time logs allow members to record hours spent on each task.",
        ],
        "features_large": [
            "Team members can create tasks and assign them to colleagues.",
            "Projects have milestones with target dates and progress tracking.",
            "File attachments can be added to tasks.",
            "Kanban boards visualize task status across workflow stages.",
            "Time logs allow members to record hours spent on each task.",
            "Gantt charts show dependencies and the critical path.",
            "Automated reports notify managers of overdue tasks and budget overruns.",
            "Integration with Slack and email sends task update notifications.",
        ],
        "nfr": "Real-time collaboration with under 100ms sync latency. Support 10,000 concurrent users. Data backup every 6 hours.",
    },
    {
        "domain": "inventory",
        "title": "Inventory & Supply Chain Management System",
        "overview": "A system for tracking inventory, managing suppliers, and automating reorders.",
        "features_small": [
            "Warehouse staff can record incoming and outgoing stock.",
            "Low-stock alerts are triggered when items fall below threshold.",
            "Purchase orders are created and sent to suppliers automatically.",
        ],
        "features_medium": [
            "Warehouse staff can record incoming and outgoing stock.",
            "Low-stock alerts are triggered when items fall below threshold.",
            "Purchase orders are created and sent to suppliers automatically.",
            "Barcode scanning speeds up stock intake and dispatch.",
            "Inventory reports show turnover rates and slow-moving items.",
        ],
        "features_large": [
            "Warehouse staff can record incoming and outgoing stock.",
            "Low-stock alerts are triggered when items fall below threshold.",
            "Purchase orders are created and sent to suppliers automatically.",
            "Barcode scanning speeds up stock intake and dispatch.",
            "Inventory reports show turnover rates and slow-moving items.",
            "Multi-warehouse transfers are tracked with full audit trail.",
            "Demand forecasting predicts stock needs based on sales trends.",
            "Supplier performance is rated on delivery time and quality.",
        ],
        "nfr": "Real-time stock counts with sub-second latency. Handle 1 million SKUs. FIFO and LIFO accounting methods supported.",
    },
    {
        "domain": "insurance",
        "title": "Insurance Claims Processing Platform",
        "overview": "A digital platform for submitting, reviewing, and settling insurance claims.",
        "features_small": [
            "Policyholders can submit claims with photos and incident descriptions.",
            "Adjusters review claims and request additional documents.",
            "Approved claims trigger automatic payment to the policyholder.",
        ],
        "features_medium": [
            "Policyholders can submit claims with photos and incident descriptions.",
            "Adjusters review claims and request additional documents.",
            "Approved claims trigger automatic payment to the policyholder.",
            "Fraud detection flags suspicious claim patterns for manual review.",
            "Policyholders track claim status and receive email notifications.",
        ],
        "features_large": [
            "Policyholders can submit claims with photos and incident descriptions.",
            "Adjusters review claims and request additional documents.",
            "Approved claims trigger automatic payment to the policyholder.",
            "Fraud detection flags suspicious claim patterns for manual review.",
            "Policyholders track claim status and receive email notifications.",
            "Third-party repair shops submit repair invoices directly to the system.",
            "Claims analytics show settlement times, fraud rates, and payouts.",
            "Policy renewal reminders are sent 30 days before expiry.",
        ],
        "nfr": "SOX compliance for financial transactions. Claims data retained 7 years. 99.95% uptime SLA.",
    },
    {
        "domain": "recruitment",
        "title": "Talent Acquisition & Recruitment Platform",
        "overview": "An end-to-end recruitment platform for posting jobs, screening candidates, and managing hiring.",
        "features_small": [
            "Recruiters can post job openings with descriptions and requirements.",
            "Candidates can apply with a CV and cover letter.",
            "Interview slots are scheduled and confirmed via email.",
        ],
        "features_medium": [
            "Recruiters can post job openings with descriptions and requirements.",
            "Candidates can apply with a CV and cover letter.",
            "Interview slots are scheduled and confirmed via email.",
            "AI screening ranks candidates based on skill match.",
            "Offer letters are generated and sent for e-signature.",
        ],
        "features_large": [
            "Recruiters can post job openings with descriptions and requirements.",
            "Candidates can apply with a CV and cover letter.",
            "Interview slots are scheduled and confirmed via email.",
            "AI screening ranks candidates based on skill match.",
            "Offer letters are generated and sent for e-signature.",
            "Background checks are initiated and tracked through third-party providers.",
            "Onboarding workflows assign equipment, accounts, and training tasks.",
            "Analytics track time-to-hire, offer acceptance rates, and source ROI.",
        ],
        "nfr": "GDPR for candidate data with right-to-erasure. 30-day data retention for rejected applicants. SSO via LinkedIn and Google.",
    },
    {
        "domain": "content_management",
        "title": "Digital Content Management System",
        "overview": "A CMS for managing web content, media assets, and publishing workflows.",
        "features_small": [
            "Editors can create, edit, and publish articles with rich text.",
            "Media library stores images and videos with search functionality.",
            "Content is previewed before publishing.",
        ],
        "features_medium": [
            "Editors can create, edit, and publish articles with rich text.",
            "Media library stores images and videos with search functionality.",
            "Content is previewed before publishing.",
            "Multi-language support allows translating content into 10 languages.",
            "Content scheduling publishes articles at a specified future date.",
        ],
        "features_large": [
            "Editors can create, edit, and publish articles with rich text.",
            "Media library stores images and videos with search functionality.",
            "Content is previewed before publishing.",
            "Multi-language support allows translating content into 10 languages.",
            "Content scheduling publishes articles at a specified future date.",
            "Version history allows reverting to previous content drafts.",
            "SEO metadata fields help optimize content for search engines.",
            "Content approval workflows require sign-off before publishing.",
        ],
        "nfr": "Page load under 1 second with CDN integration. Support 10TB media storage. WCAG 2.1 AA accessibility compliance.",
    },
    {
        "domain": "banking",
        "title": "Digital Banking Mobile Application",
        "overview": "A mobile banking app for retail customers to manage accounts and transactions.",
        "features_small": [
            "Customers can view account balances and transaction history.",
            "Fund transfers between accounts are processed instantly.",
            "Bill payments are scheduled for recurring expenses.",
        ],
        "features_medium": [
            "Customers can view account balances and transaction history.",
            "Fund transfers between accounts are processed instantly.",
            "Bill payments are scheduled for recurring expenses.",
            "Instant notifications are sent for every debit and credit.",
            "Customers can block and unblock their debit cards.",
        ],
        "features_large": [
            "Customers can view account balances and transaction history.",
            "Fund transfers between accounts are processed instantly.",
            "Bill payments are scheduled for recurring expenses.",
            "Instant notifications are sent for every debit and credit.",
            "Customers can block and unblock their debit cards.",
            "Biometric login with fingerprint and face recognition is supported.",
            "Spending analytics categorize transactions and show monthly budgets.",
            "International wire transfers support SWIFT and SEPA protocols.",
        ],
        "nfr": "PCI-DSS Level 1 compliance. End-to-end encryption for all transactions. Biometric authentication must respond in under 300ms.",
    },
    {
        "domain": "gaming",
        "title": "Multiplayer Online Game Platform",
        "overview": "A backend platform for hosting multiplayer games with matchmaking and leaderboards.",
        "features_small": [
            "Players register and create game profiles with usernames.",
            "Matchmaking pairs players of similar skill for ranked games.",
            "Leaderboards display top players globally and by region.",
        ],
        "features_medium": [
            "Players register and create game profiles with usernames.",
            "Matchmaking pairs players of similar skill for ranked games.",
            "Leaderboards display top players globally and by region.",
            "In-game purchases allow players to buy cosmetic items.",
            "Anti-cheat detection flags suspicious player behavior.",
        ],
        "features_large": [
            "Players register and create game profiles with usernames.",
            "Matchmaking pairs players of similar skill for ranked games.",
            "Leaderboards display top players globally and by region.",
            "In-game purchases allow players to buy cosmetic items.",
            "Anti-cheat detection flags suspicious player behavior.",
            "Tournaments are organized with brackets, schedules, and prize pools.",
            "Replay files are stored and accessible for analysis.",
            "Cross-platform play supports PC, console, and mobile clients.",
        ],
        "nfr": "Match server latency under 50ms. Support 1 million concurrent players. 99.99% uptime during tournament events.",
    },
    {
        "domain": "government",
        "title": "Citizen Services Portal",
        "overview": "A government e-services portal for citizens to access and submit official requests.",
        "features_small": [
            "Citizens can apply for permits and licenses online.",
            "Applications are tracked with status updates and notifications.",
            "Government staff review and approve applications through a dashboard.",
        ],
        "features_medium": [
            "Citizens can apply for permits and licenses online.",
            "Applications are tracked with status updates and notifications.",
            "Government staff review and approve applications through a dashboard.",
            "Digital identity verification uses national ID number validation.",
            "Fee payments are processed through integrated payment gateways.",
        ],
        "features_large": [
            "Citizens can apply for permits and licenses online.",
            "Applications are tracked with status updates and notifications.",
            "Government staff review and approve applications through a dashboard.",
            "Digital identity verification uses national ID number validation.",
            "Fee payments are processed through integrated payment gateways.",
            "Appeals can be submitted and reviewed through a dedicated workflow.",
            "Multilingual support provides Arabic and English interfaces.",
            "Audit logs capture all access and changes to citizen records.",
        ],
        "nfr": "ISO 27001 compliance. Accessibility to WCAG 2.1 AA. Data sovereignty requires all data stored within national borders.",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Extended domains -- new compact format: all_features[0:14], auto-sized
# ─────────────────────────────────────────────────────────────────────────────
EXTENDED_DOMAINS: list[dict] = [
    {
        "domain": "pharmacy_management",
        "title": "Pharmacy Management System",
        "overview": "A digital system for managing prescriptions, drug inventory, and patient billing at pharmacies.",
        "all_features": [
            "Pharmacists can receive and process electronic prescriptions from doctors.",
            "Drug inventory is tracked with expiry date monitoring and reorder alerts.",
            "Customer purchase history is stored for repeat prescription refills.",
            "Billing generates itemized receipts and processes insurance claims.",
            "Drug interaction warnings are displayed when dispensing combinations.",
            "Controlled substance dispensing is logged with pharmacist sign-off.",
            "Suppliers receive automated purchase orders when stock falls below threshold.",
            "Customers receive SMS reminders when prescriptions are ready for pickup.",
            "Pharmacists can process partial fills and track outstanding quantities.",
            "Daily sales reports summarize revenue by drug category and prescriber.",
            "Cold-chain medications are tracked with temperature log requirements.",
            "Pharmacy manager can configure pricing tiers for different insurance plans.",
            "Patient allergy profiles are checked before dispensing new medications.",
            "Monthly controlled-substance reports are generated for regulatory submission.",
        ],
        "nfr": "FDA CFR 21 Part 11 e-signature compliance. HIPAA for patient records. Drug database updated daily. Audit trail for all dispensing events.",
    },
    {
        "domain": "dental_clinic",
        "title": "Dental Clinic Management System",
        "overview": "A management platform for dental practices to handle appointments, patient records, and billing.",
        "all_features": [
            "Patients can book appointments online and receive confirmation emails.",
            "Dentists can view and update patient dental records and treatment history.",
            "X-ray images are uploaded, stored, and linked to patient records.",
            "Treatment plans are created with estimated costs and insurance coverage.",
            "Insurance claims are submitted electronically and tracked for reimbursement.",
            "Automated reminders are sent 48 hours before scheduled appointments.",
            "Receptionist can manage chair schedules and dentist availability.",
            "Patient billing shows itemized procedures with insurance deductions.",
            "Lab orders for crowns and implants are sent to external dental labs.",
            "New patient intake forms are completed digitally before the first visit.",
            "Analytics show appointment no-show rates and revenue per dentist.",
            "Dentists can add clinical notes using voice-to-text transcription.",
            "Referral letters are generated for specialist consultations.",
            "Patient satisfaction surveys are sent after completed appointments.",
        ],
        "nfr": "HIPAA compliance for all PHI. Radiograph images stored DICOM-compatible. Concurrent scheduling for up to 20 chairs. Data backup nightly.",
    },
    {
        "domain": "fitness_gym",
        "title": "Gym and Fitness Center Management Platform",
        "overview": "A platform for managing gym memberships, class bookings, and trainer scheduling.",
        "all_features": [
            "Members can purchase and manage gym memberships online.",
            "Class schedules are published and members can book slots in advance.",
            "Trainers can manage their weekly availability and client sessions.",
            "Entry gate is controlled via QR-code membership scan.",
            "Automated renewals charge members before membership expiry.",
            "Nutritional plans and workout programs are assigned by trainers.",
            "Members track workout history, body metrics, and progress photos.",
            "Point-of-sale handles supplement and equipment purchases at the front desk.",
            "Waitlists fill canceled class slots automatically from the queue.",
            "Manager views occupancy heatmaps showing peak usage hours.",
            "Corporate membership packages allow companies to enroll multiple employees.",
            "Loyalty points reward consistent attendance and redeemable for merchandise.",
            "Automated suspension messages are sent when payments fail after retry.",
            "Annual facility usage reports are generated for business planning.",
        ],
        "nfr": "Gate scan response under 500ms. Support 5,000 concurrent active members. PCI-DSS for payment processing. Mobile app for iOS and Android.",
    },
    {
        "domain": "mental_health_app",
        "title": "Mental Health and Therapy Platform",
        "overview": "A digital mental health platform connecting users with therapists for virtual therapy sessions.",
        "all_features": [
            "Users complete an onboarding assessment to be matched with a therapist.",
            "Video therapy sessions are conducted through an encrypted video interface.",
            "Users log daily mood, sleep, and anxiety levels in a wellness journal.",
            "Therapists create and assign evidence-based exercises between sessions.",
            "Crisis hotline integration escalates high-risk users to emergency support.",
            "Progress tracking shows mood trends over weeks and months.",
            "Therapists maintain confidential session notes visible only to them.",
            "Billing handles insurance verification and co-pay collection.",
            "Peer support groups allow moderated group chat sessions.",
            "Mindfulness audio sessions and breathing exercises are available on demand.",
            "Therapists can share secure documents and worksheets with clients.",
            "Supervisors review anonymized outcomes to ensure care quality.",
            "Reminder notifications support adherence to daily wellness habits.",
            "Users can pause or cancel therapy services with data export option.",
        ],
        "nfr": "HIPAA and HITECH compliance. End-to-end encryption for all communications. Zero-retention policy for video calls. WCAG 2.1 AA accessibility.",
    },
    {
        "domain": "lab_diagnostics",
        "title": "Medical Laboratory Information System",
        "overview": "A system for managing lab test orders, sample tracking, and result reporting in clinical labs.",
        "all_features": [
            "Doctors can submit test orders electronically linked to patient records.",
            "Sample collection barcodes are generated and printed at collection points.",
            "Sample status is tracked from collection through analysis to reporting.",
            "Lab technicians record test results and flag abnormal values.",
            "Results are automatically forwarded to the ordering physician.",
            "Critical values trigger immediate phone-call alert to the doctor.",
            "Equipment interfaces automatically import analyzer results.",
            "Quality control samples validate accuracy before patient runs.",
            "Turnaround time dashboards track SLA compliance per test type.",
            "Patients can view their results through a secure online portal.",
            "Billing generates invoices for tests and submits to insurance.",
            "Reagent inventory is monitored with restocking alerts.",
            "Accreditation reports export all QC data in ISO 15189 format.",
            "Reference ranges are configurable per patient age and gender.",
        ],
        "nfr": "HL7 FHIR integration with hospital EMR. CAP/ISO 15189 compliance. 99.9% system uptime. Audit trail for all result modifications.",
    },
    {
        "domain": "blood_bank",
        "title": "Blood Bank Management System",
        "overview": "A system for managing blood donations, inventory, and transfusion requests in blood banks.",
        "all_features": [
            "Donors register and schedule blood donation appointments.",
            "Donor eligibility is screened based on health criteria and donation history.",
            "Collected blood units are labeled with blood type and donor information.",
            "Units undergo mandatory infectious disease testing with result tracking.",
            "Blood inventory is tracked by type, component, and expiry date.",
            "Hospital transfusion requests are matched against available inventory.",
            "Cross-match compatibility is recorded before units are issued.",
            "Issued units are tracked to the recipient patient for traceability.",
            "FIFO dispatch ensures older units are used before newer stock.",
            "Low-inventory alerts trigger donor recruitment campaigns.",
            "Discarded units are logged with reason for wastage reporting.",
            "Regional blood centers share inventory visibility for emergency transfers.",
            "Monthly statistics report donations, usage, and wastage by component.",
            "Donors receive post-donation certificates and next-eligible-date reminders.",
        ],
        "nfr": "FDA 21 CFR 606 compliance. Full traceability from donor to recipient. Barcode scanning for all unit tracking. Data retained 10 years.",
    },
    {
        "domain": "veterinary_clinic",
        "title": "Veterinary Clinic Management System",
        "overview": "A platform for managing pet registrations, veterinary appointments, and treatment records.",
        "all_features": [
            "Pet owners register their animals with breed, age, and medical history.",
            "Appointments are booked online for consultations and procedures.",
            "Veterinarians record examination findings and diagnoses per visit.",
            "Vaccination records are tracked with automated reminder emails.",
            "Prescriptions are generated and dispensed from in-clinic pharmacy.",
            "Diagnostic imaging files are attached to patient records.",
            "Lab test orders are sent to in-house or external laboratories.",
            "Surgical procedures are logged with anesthesia and post-op notes.",
            "Boarding reservations track pets staying overnight in the clinic.",
            "Pet owners access their animal's records through a client portal.",
            "Billing generates itemized invoices and processes pet insurance claims.",
            "Reminder campaigns target overdue vaccinations and annual check-ups.",
            "Inventory tracks medical supplies and alerts on low stock.",
            "Monthly revenue reports break down income by service category.",
        ],
        "nfr": "GDPR for pet owner data. Medical records retained 7 years. Mobile-friendly booking portal. SMS and email notifications.",
    },
    {
        "domain": "stock_trading",
        "title": "Online Stock Trading Platform",
        "overview": "A retail brokerage platform for buying, selling, and tracking stocks and ETFs.",
        "all_features": [
            "Users open brokerage accounts with identity verification and KYC.",
            "Real-time stock quotes and charts are displayed on the trading dashboard.",
            "Users place market, limit, and stop-loss orders for stocks and ETFs.",
            "Order confirmation and trade execution are sent via push notification.",
            "Portfolio dashboard shows holdings, market value, and daily profit and loss.",
            "Dividend payments are credited and recorded in the account statement.",
            "Users fund accounts via bank transfer and withdraw proceeds.",
            "Watchlists allow tracking of stocks not yet in the portfolio.",
            "Tax reports generate capital gains statements for annual filing.",
            "Company financial summaries and analyst ratings are shown per stock.",
            "Risk disclosure and margin trading agreements are signed digitally.",
            "Two-factor authentication secures all login and transaction events.",
            "Fractional share purchasing enables investing with small amounts.",
            "Regulatory transaction reports are generated for compliance submissions.",
        ],
        "nfr": "SEC/FINRA compliance. Order execution latency under 100ms. End-to-end TLS. 99.99% uptime during market hours. SIPC insurance disclosure.",
    },
    {
        "domain": "personal_finance",
        "title": "Personal Finance and Budgeting App",
        "overview": "A personal finance app that helps users track expenses, manage budgets, and reach savings goals.",
        "all_features": [
            "Users connect bank accounts and credit cards for transaction import.",
            "Transactions are automatically categorized by type and merchant.",
            "Monthly budgets are set per spending category with progress indicators.",
            "Spending insights show trends and highlight overspending categories.",
            "Savings goals track progress toward targets like vacations or emergencies.",
            "Recurring bills are detected and upcoming payments are listed.",
            "Net worth calculation aggregates assets and liabilities in real time.",
            "Users set financial goals with timelines and recommended monthly savings.",
            "Credit score monitoring shows changes with explanation of factors.",
            "Investment account summaries show portfolio performance alongside spending.",
            "Custom reports export transaction history as CSV for tax purposes.",
            "Shared household budgets allow multiple members to track joint expenses.",
            "AI spending coach sends weekly suggestions to improve financial health.",
            "Data export and account deletion honor right-to-erasure requests.",
        ],
        "nfr": "PSD2/Open Banking compliance for account aggregation. AES-256 encryption for financial data. Read-only bank access via OAuth 2.0. GDPR compliant.",
    },
    {
        "domain": "loan_management",
        "title": "Loan Origination and Management System",
        "overview": "A financial system for processing loan applications, disbursements, and repayment tracking.",
        "all_features": [
            "Borrowers submit loan applications with income and employment details.",
            "Credit scoring integrates with bureau APIs to assess creditworthiness.",
            "Underwriters review applications and set loan terms and interest rates.",
            "Loan agreements are generated and signed electronically.",
            "Funds are disbursed to borrower bank accounts upon final approval.",
            "Repayment schedules show EMI amounts and due dates.",
            "Automated debits collect monthly repayments on scheduled dates.",
            "Overdue accounts trigger escalating reminder messages.",
            "Loan officers can restructure repayment plans for distressed borrowers.",
            "Collateral assets are registered and tracked for secured loans.",
            "Partial prepayments recalculate the remaining schedule automatically.",
            "Portfolio dashboards show delinquency rates, defaults, and provisioning.",
            "Loan officers track application pipeline from submission to disbursement.",
            "Regulatory reports generate non-performing loan classifications monthly.",
        ],
        "nfr": "Basel III reporting compliance. Audit trail for all approval decisions. Encryption for PII fields. 99.9% uptime for payment processing gateway.",
    },
    {
        "domain": "crowdfunding",
        "title": "Crowdfunding Platform",
        "overview": "An online crowdfunding platform for creative projects and charitable causes.",
        "all_features": [
            "Project creators launch campaigns with goals, descriptions, and reward tiers.",
            "Backers pledge money to campaigns and select reward tiers.",
            "Payment processing holds pledges until campaign goal is reached.",
            "Backers receive updates when project milestones are announced.",
            "Campaigns that fail to meet goals refund all pledges automatically.",
            "Project creators provide progress updates and media posts during campaigns.",
            "Backer comments allow community discussion on campaign pages.",
            "Fraud detection flags campaigns with suspicious activity patterns.",
            "Platform fees are deducted from successful campaign payouts.",
            "Social sharing links promote campaigns on social media.",
            "Analytics dashboards show campaign traffic, conversion, and referral sources.",
            "Project creators submit proof of delivery for physical rewards.",
            "Charity campaigns issue tax receipts to eligible donors.",
            "Creator identity verification prevents duplicate or fraudulent accounts.",
        ],
        "nfr": "PCI-DSS Level 1 payment processing. GDPR for backer data. Payment holds in escrow. Refund processing within 5-10 business days.",
    },
    {
        "domain": "travel_booking",
        "title": "Travel Booking and Itinerary Management Platform",
        "overview": "An online travel platform for searching, booking, and managing flights, hotels, and packages.",
        "all_features": [
            "Users search for flights by origin, destination, date, and passenger count.",
            "Flight search results are displayed with price, duration, and airline filters.",
            "Users book flights and receive e-ticket confirmations via email.",
            "Hotel searches show availability, pricing, and guest ratings by location.",
            "Hotel reservations are made with cancellation policy displayed prominently.",
            "Multi-destination itineraries combine flights, hotels, and car rentals.",
            "Travel insurance options are offered at checkout.",
            "Booking management allows users to modify or cancel reservations.",
            "Price alerts notify users when fares drop for saved routes.",
            "Loyalty points are earned per booking and redeemed for discounts.",
            "Group bookings handle multiple passengers with seat selection.",
            "Corporate travel policies restrict bookings outside approved vendors.",
            "Trip expense reports are exported for corporate reimbursement.",
            "Visa requirement information is shown based on passport and destination.",
        ],
        "nfr": "GDS integration for real-time inventory. PCI-DSS for payment. PNR handling via IATA standards. Search results in under 2 seconds.",
    },
    {
        "domain": "hotel_management",
        "title": "Hotel Property Management System",
        "overview": "An end-to-end PMS for managing hotel reservations, front desk, housekeeping, and billing.",
        "all_features": [
            "Front desk staff manage check-in, check-out, and room assignments.",
            "Online reservations sync in real time from OTA channels and the hotel website.",
            "Room availability calendar shows occupancy by room type and date.",
            "Housekeeping schedules assign room-cleaning tasks to staff.",
            "Minibar and room service charges are added to the guest folio.",
            "Group bookings handle block reservations with dedicated block codes.",
            "Invoice generation at checkout includes all room charges and taxes.",
            "Guest profiles store preferences for personalized service on return visits.",
            "Revenue manager sets dynamic pricing rules based on occupancy and demand.",
            "Maintenance requests are logged and assigned to the engineering team.",
            "Restaurant POS integrates with the PMS for unified guest billing.",
            "Night audit automated reconciliation closes the day and generates reports.",
            "Channel manager distributes room inventory to OTA platforms.",
            "Guest satisfaction scores are collected post-checkout for review.",
        ],
        "nfr": "PCI-DSS for credit card tokenization. PMS must integrate with OTA via channel manager API. Reservation sync latency under 5 seconds.",
    },
    {
        "domain": "car_rental",
        "title": "Car Rental Management System",
        "overview": "A platform for managing vehicle rentals, reservations, fleet maintenance, and customer billing.",
        "all_features": [
            "Customers search for available vehicles by location, date, and category.",
            "Reservations are confirmed with vehicle details and pickup instructions.",
            "Customer identity and license verification is performed at pickup.",
            "Rental agreements are signed digitally at the counter or online.",
            "Fuel levels and vehicle condition are recorded at pickup and return.",
            "GPS tracking monitors vehicle location for fleet visibility.",
            "Mileage and damage charges are calculated automatically at return.",
            "Invoices are generated with base rental, extras, and applicable taxes.",
            "Fleet maintenance schedules are tracked with service due-date alerts.",
            "Corporate accounts receive monthly consolidated invoices.",
            "Dynamic pricing adjusts rates based on demand and vehicle availability.",
            "Vehicle utilization reports show revenue per vehicle and idle days.",
            "Insurance add-ons are offered and linked to rental contracts.",
            "Late return notifications are sent with accumulating hourly charges.",
        ],
        "nfr": "PCI-DSS for payment. GPS data streamed every 60 seconds. Fleet size scalable to 100,000 vehicles. GDPR for customer identity records.",
    },
    {
        "domain": "tour_operator",
        "title": "Tour Operator and Package Management System",
        "overview": "A system for creating, selling, and operating packaged tours with itinerary management.",
        "all_features": [
            "Tour operators create packages with day-by-day itineraries and pricing.",
            "Customers browse and book tour packages with instant confirmation.",
            "Tour availability is managed with seat limits and waitlist support.",
            "Booking system collects passenger information and dietary preferences.",
            "Guides are assigned to tours with schedule visibility on a mobile app.",
            "Vouchers are issued for accommodation and activity inclusions.",
            "Customer documents such as passports and visas are collected before departure.",
            "Real-time location sharing allows tour leaders to communicate with office.",
            "Post-tour surveys collect ratings for guides, hotels, and activities.",
            "Cancellation and amendment policies are enforced with automated refunds.",
            "Supplier invoices for hotels and transport are matched against bookings.",
            "Revenue reports compare planned versus actual costs per tour.",
            "Multi-currency pricing supports international markets.",
            "Repeat customer discounts are applied automatically during checkout.",
        ],
        "nfr": "GDPR for traveler personal data. Payment integration with multi-currency support. Mobile guide app works offline for remote destinations.",
    },
    {
        "domain": "online_exam",
        "title": "Online Examination and Assessment Platform",
        "overview": "A proctored online exam platform for conducting assessments at scale.",
        "all_features": [
            "Instructors create exams with multiple choice, essay, and coding question types.",
            "Students access exams during defined time windows with countdown timers.",
            "Randomized question order and answer shuffling prevent copying.",
            "Automated grading scores multiple-choice and true/false questions instantly.",
            "Plagiarism detection compares essay responses against a reference database.",
            "Live proctoring monitors webcam and screen activity during exams.",
            "AI flags suspicious behaviors such as tab switches and face detection loss.",
            "Results are released on a schedule or immediately after submission.",
            "Detailed performance analytics show question-level difficulty and pass rates.",
            "Accessibility features include extended time and screen-reader compatibility.",
            "Question banks allow instructors to reuse and tag questions by topic.",
            "Certificates are auto-generated and emailed to passing candidates.",
            "Retake policies limit the number of attempts per candidate.",
            "Admin dashboards monitor live exam sessions and handle technical issues.",
        ],
        "nfr": "99.9% uptime during exam windows. WebRTC for proctoring with sub-500ms latency. GDPR for candidate data. AES-256 for exam content at rest.",
    },
    {
        "domain": "tutoring_platform",
        "title": "Online Tutoring and Private Lessons Platform",
        "overview": "A marketplace connecting students with tutors for live one-on-one and group online lessons.",
        "all_features": [
            "Students search for tutors by subject, language, and hourly rate.",
            "Tutor profiles display qualifications, reviews, and availability calendar.",
            "Trial sessions allow students to sample a tutor before committing.",
            "Video lessons are conducted through an integrated whiteboard and video tool.",
            "Lesson recordings are available to students for review after the session.",
            "Parents can monitor their child's lesson history and progress reports.",
            "Automated billing charges students after each completed session.",
            "Tutors set their schedules and receive booking requests.",
            "Rating and review system allows students to rate tutors after lessons.",
            "Group lessons allow up to 10 students per session at reduced per-student rates.",
            "Learning plans track student progress toward defined goals.",
            "Messaging system allows pre-lesson preparation between tutor and student.",
            "Tutors withdraw earnings weekly via bank transfer or digital wallet.",
            "Dispute resolution process handles refund requests for missed or poor sessions.",
        ],
        "nfr": "COPPA compliance for students under 13. Video quality minimum 720p. Platform fee 15% per session. GDPR for user data.",
    },
    {
        "domain": "university_portal",
        "title": "University Student Information System",
        "overview": "A comprehensive student portal for enrollment, academic records, and campus services.",
        "all_features": [
            "Students enroll in courses each semester with prerequisite enforcement.",
            "Academic transcripts are generated and verified digitally.",
            "Faculty post grades and attendance records through the portal.",
            "Students pay tuition fees online and access fee receipts.",
            "Scholarship applications are submitted and tracked through the system.",
            "Library services allow book searches, reservations, and renewals online.",
            "Dormitory assignments and applications are managed through the portal.",
            "Event calendar lists upcoming academic and extracurricular activities.",
            "Graduation applications trigger degree audit and completion verification.",
            "International student visa letter requests are processed through the portal.",
            "Alumni network access is granted after graduation for career resources.",
            "Anonymous course evaluation surveys are submitted by students each term.",
            "Department administrators manage faculty workloads and course assignments.",
            "Accreditation reports aggregate enrollment, outcomes, and completion data.",
        ],
        "nfr": "FERPA compliance for student records. SSO integration with university identity provider. Scalable for 50,000 concurrent users during enrollment.",
    },
    {
        "domain": "language_learning",
        "title": "Language Learning Application",
        "overview": "A gamified language learning app for building vocabulary, grammar, and conversation skills.",
        "all_features": [
            "Users select a target language and set daily practice goals.",
            "Adaptive exercises cover vocabulary, grammar, and listening comprehension.",
            "Spaced repetition surfaces flashcards at optimal review intervals.",
            "Speaking exercises use speech recognition to evaluate pronunciation.",
            "Gamification awards XP, streaks, and badges for consistent practice.",
            "Leaderboards show rankings within friend groups and global tiers.",
            "Live conversation practice connects learners with native speaker tutors.",
            "Lesson paths adapt to the learner's proficiency test results.",
            "Offline mode downloads lessons for practice without internet.",
            "Progress reports show vocabulary acquired, accuracy, and time spent.",
            "Content is organized by CEFR levels from A1 to C2.",
            "Parents monitor children's daily progress and set usage time limits.",
            "Subscription plans unlock advanced content and conversation sessions.",
            "Community forums allow learners to ask questions in their target language.",
        ],
        "nfr": "Speech recognition accuracy above 90% for supported languages. Offline sync within 30 seconds of reconnecting. COPPA for under-13 users.",
    },
    {
        "domain": "corporate_training",
        "title": "Corporate Learning and Development Platform",
        "overview": "An LMS for companies to deliver employee training, track compliance, and measure skill development.",
        "all_features": [
            "HR managers create training programs and assign courses to employee groups.",
            "Employees access e-learning courses with video, slides, and quizzes.",
            "Course completion is tracked and certificate is issued on passing.",
            "Compliance training deadlines trigger automated reminders.",
            "Managers view team training completion rates on a dashboard.",
            "Skill gap analysis compares employee competencies against role requirements.",
            "External training providers upload accredited courses to the marketplace.",
            "Blended learning combines online modules with in-person workshop scheduling.",
            "Social learning features allow employees to share notes and discuss courses.",
            "Learning paths auto-recommend next courses based on role and completed modules.",
            "SCORM and xAPI content from third-party tools is imported seamlessly.",
            "360-degree feedback surveys collect peer input on post-training performance.",
            "Budget tracking shows training spend per department and cost per completion.",
            "Annual training reports satisfy regulatory audit requirements.",
        ],
        "nfr": "SCORM 1.2 and xAPI compliance. SSO via SAML 2.0. Supports 100,000 concurrent learners. GDPR for employee learning records.",
    },
    {
        "domain": "production_planning",
        "title": "Manufacturing Production Planning System",
        "overview": "A system for scheduling production runs, managing work orders, and tracking factory output.",
        "all_features": [
            "Production planners create work orders linked to customer sales orders.",
            "Bill of materials is validated before releasing work orders to the floor.",
            "Machine capacity is loaded and scheduled to prevent bottlenecks.",
            "Shop floor operators update work order status at each production stage.",
            "Material availability is checked against open work orders in real time.",
            "Production yield and scrap rates are recorded per batch.",
            "Quality hold orders pause batches pending inspection approval.",
            "Shift handover reports summarize output, issues, and pending work.",
            "OEE (overall equipment effectiveness) is calculated per machine daily.",
            "Maintenance downtime is logged and deducted from capacity planning.",
            "Rescheduling engine recalculates the plan when delays occur.",
            "Cost variance reports compare actual versus standard production costs.",
            "Supplier lead times are tracked and factored into material planning.",
            "Monthly production reports show on-time delivery rate and throughput.",
        ],
        "nfr": "ERP integration via REST API. MRP run must complete within 5 minutes for 10,000 SKUs. Audit trail for all BOM changes. 99.9% uptime.",
    },
    {
        "domain": "quality_control_system",
        "title": "Quality Control and Inspection Management System",
        "overview": "A system for managing product inspections, non-conformances, and quality certifications.",
        "all_features": [
            "Inspectors record incoming material inspections with pass/fail results.",
            "In-process inspections are triggered at defined production checkpoints.",
            "Non-conformance reports are raised for defective items.",
            "Root cause analysis workflows guide corrective action investigations.",
            "Corrective actions are assigned, tracked, and verified for closure.",
            "Statistical process control charts monitor process stability.",
            "Customer complaints are logged and linked to product batches.",
            "Supplier quality audits are scheduled and findings recorded.",
            "Product release is blocked until all required inspections are approved.",
            "Inspection checklists are configured per product type and stage.",
            "Calibration records track instrument validity and due-date alerts.",
            "Quality metrics dashboards show defect rates, PPM, and DPMO.",
            "ISO 9001 audit evidence is compiled and exported for certification.",
            "Warranty return analysis links field failures back to production batches.",
        ],
        "nfr": "ISO 9001:2015 compliance. Full traceability from raw material to finished product. Audit logs retained 5 years. Mobile-friendly inspection forms.",
    },
    {
        "domain": "maintenance_management",
        "title": "Computerized Maintenance Management System",
        "overview": "A CMMS for managing asset maintenance, work orders, and spare parts for industrial facilities.",
        "all_features": [
            "Assets are registered with specifications, location, and maintenance history.",
            "Preventive maintenance schedules are created based on time or usage triggers.",
            "Work orders are generated automatically for overdue maintenance tasks.",
            "Technicians receive mobile work orders and update status from the field.",
            "Spare parts inventory is tracked and reserved for open work orders.",
            "Breakdown notifications are sent to supervisors for critical asset failures.",
            "Root cause codes are recorded when closing corrective maintenance jobs.",
            "Contractors receive work orders electronically and submit completion reports.",
            "Calibration schedules track instruments with regulatory traceability.",
            "Asset lifecycle cost analysis compares maintenance versus replacement cost.",
            "KPIs track mean time to repair, mean time between failures, and maintenance ratios.",
            "Purchase requisitions are auto-generated when spare parts fall below minimum.",
            "Maintenance history exports support warranty claims and audits.",
            "Annual maintenance budget reports compare actuals to plan by asset category.",
        ],
        "nfr": "Integration with ERP for purchase requisitions. Mobile app with offline capability. Barcode scanning for asset and parts lookup. 99.9% uptime.",
    },
    {
        "domain": "music_streaming",
        "title": "Music Streaming Service",
        "overview": "A music streaming platform for discovering, playing, and sharing music across devices.",
        "all_features": [
            "Users stream songs, albums, and playlists on demand.",
            "Personalized recommendations surface new music based on listening history.",
            "Users create and share playlists with followers.",
            "Artist profiles display discography, bio, and upcoming events.",
            "Offline downloads allow listening without an internet connection.",
            "Lyrics display synchronized with the current playback position.",
            "Social features show what friends are listening to in real time.",
            "Podcast episodes are available alongside music in a unified library.",
            "Radio stations are generated from a seed track or artist.",
            "High-fidelity audio is offered as a premium subscription tier.",
            "Cross-device playback continues seamlessly across phone, desktop, and TV.",
            "Artist royalty reports track streams and calculate revenue shares.",
            "Parental controls filter explicit content for family accounts.",
            "User listening statistics are shared as an annual personalized summary.",
        ],
        "nfr": "Audio latency under 2 seconds. CDN delivers content in under 1 second globally. 99.99% uptime. DRM for licensed content. GDPR for listening data.",
    },
    {
        "domain": "video_on_demand",
        "title": "Video Streaming and On-Demand Platform",
        "overview": "A VOD platform for publishing, streaming, and monetizing video content.",
        "all_features": [
            "Content creators upload and publish video episodes and series.",
            "Viewers browse content by genre, rating, and trending.",
            "Adaptive bitrate streaming adjusts quality to connection speed.",
            "Subscription plans provide unlimited streaming for a monthly fee.",
            "Pay-per-view options allow one-time rental of new releases.",
            "Subtitles and closed captions are supported in multiple languages.",
            "Parental controls allow restricting content by maturity rating.",
            "Watchlist allows users to save content to watch later.",
            "Continue watching feature resumes from the last viewed position.",
            "Download for offline viewing is available for subscribers.",
            "Analytics show unique viewers, completion rates, and engagement per title.",
            "DRM prevents unauthorized copying and distribution of content.",
            "Advertising-supported tier shows pre-roll and mid-roll ads.",
            "Creator revenue sharing is calculated from views and subscriptions.",
        ],
        "nfr": "4K HDR streaming at 25 Mbps. DRM via Widevine and FairPlay. CDN latency under 500ms. GDPR for viewer data. 99.95% uptime SLA.",
    },
    {
        "domain": "podcast_platform",
        "title": "Podcast Hosting and Discovery Platform",
        "overview": "A podcast platform for hosting, distributing, and discovering audio shows.",
        "all_features": [
            "Podcasters upload episodes and configure show metadata and artwork.",
            "RSS feeds are automatically generated for distribution to podcast apps.",
            "Listeners search and subscribe to shows by category and keyword.",
            "Episode streaming and download are available to all users.",
            "Chapters and timestamps allow listeners to skip to specific segments.",
            "Transcript generation provides text versions of episodes for accessibility.",
            "Listen-through rates and drop-off analytics are shown to podcasters.",
            "Monetization allows podcasters to offer premium subscriber-only episodes.",
            "Dynamic ad insertion places ads in episodes programmatically.",
            "Episode playlists allow listeners to queue multiple shows.",
            "Cross-promotion tools let podcasters recommend other shows.",
            "Podcast website generator creates a landing page from show metadata.",
            "Guest booking integration helps podcasters schedule interview guests.",
            "Annual top-chart rankings highlight trending shows across categories.",
        ],
        "nfr": "Audio CDN delivers within 1 second globally. RSS spec RFC 4287 compliance. Unlimited storage for Premium tier. GDPR for listener analytics.",
    },
    {
        "domain": "ride_hailing",
        "title": "Ride-Hailing Mobile Platform",
        "overview": "A ride-hailing app connecting passengers with drivers for on-demand transportation.",
        "all_features": [
            "Passengers request rides by entering pickup and drop-off locations.",
            "Nearest available driver is matched and notified of the request.",
            "Passengers track driver location in real time on a map.",
            "Fare estimation is shown before confirming the ride.",
            "Payment is processed automatically at trip completion via in-app wallet.",
            "Passengers and drivers rate each other after each completed trip.",
            "Promo codes and referral discounts are applied at checkout.",
            "Scheduled rides allow passengers to book in advance.",
            "Driver app manages availability, navigation, and earnings dashboard.",
            "Safety features include ride-sharing with trusted contacts and SOS button.",
            "Surge pricing activates during high-demand periods with visible multiplier.",
            "Trip history and receipts are accessible for all past rides.",
            "Driver onboarding verifies license, insurance, and vehicle inspection.",
            "City-level reporting aggregates trips, revenue, and driver activity for operations.",
        ],
        "nfr": "GPS location updates every 5 seconds. Match algorithm under 3 seconds. PCI-DSS for payments. 99.9% uptime during peak hours. GDPR.",
    },
    {
        "domain": "bike_sharing",
        "title": "Bike-Sharing and Micro-Mobility System",
        "overview": "A smart bike-sharing platform for urban mobility with docking stations and free-floating bikes.",
        "all_features": [
            "Users locate nearby bikes and docking stations via a map interface.",
            "QR code scanning unlocks bikes through the mobile app.",
            "Ride time and distance are tracked with per-minute billing.",
            "Bikes are locked at any docking station or authorized parking zone.",
            "Payment is collected via in-app wallet or card at trip end.",
            "Fleet operations team views real-time bike distribution across the city.",
            "Low-battery bikes are flagged for rebalancing by field technicians.",
            "Maintenance reports are raised by riders or staff for damaged bikes.",
            "Monthly subscriber plans offer unlimited short trips.",
            "Helmet rental can be added as an optional accessory.",
            "Corporate partnerships offer employee commuting subscriptions.",
            "Usage heatmaps identify high-demand areas for station expansion.",
            "Eco-impact metrics show CO2 saved per ride compared to car travel.",
            "Seasonal pricing adjusts rates based on weather and demand patterns.",
        ],
        "nfr": "IoT lock commands respond within 2 seconds. GPS accuracy within 3 meters. Fleet of 50,000 bikes supported. GDPR for trip data.",
    },
    {
        "domain": "parking_system",
        "title": "Smart Parking Management System",
        "overview": "A digital platform for managing parking lots, reservations, and automated access control.",
        "all_features": [
            "Drivers search and reserve parking spots in advance via the app.",
            "License plate recognition automates entry and exit without tickets.",
            "Parking duration and fees are calculated based on actual stay time.",
            "Payment is processed via in-app wallet or at exit kiosks.",
            "Parking availability is updated in real time as spots fill.",
            "Monthly passes are sold for regular commuters.",
            "EV charging spots are bookable and billing includes charging fees.",
            "Validation coupons allow businesses to subsidize visitor parking.",
            "Security cameras monitor the facility with incident logging.",
            "Operations dashboard shows occupancy rates and revenue per lot.",
            "Overstay alerts notify drivers when the reserved time is about to expire.",
            "Multi-facility management supports multiple parking lots under one account.",
            "Integration with navigation apps directs drivers to the reserved spot.",
            "Revenue reports break down income by spot type and payment method.",
        ],
        "nfr": "LPR response under 1 second for barrier control. Payment processing under 2 seconds. Uptime 99.95%. GDPR for license plate images.",
    },
    {
        "domain": "freelance_marketplace",
        "title": "Freelance Talent Marketplace",
        "overview": "An online marketplace connecting businesses with freelancers for project-based work.",
        "all_features": [
            "Freelancers create profiles with skills, portfolio, and hourly rates.",
            "Clients post project briefs and receive proposals from freelancers.",
            "Proposals include cover letter, timeline, and fixed or hourly budget.",
            "Escrow holds client payment until project milestones are approved.",
            "Messaging allows real-time communication between client and freelancer.",
            "Contract terms are agreed upon and stored as project agreements.",
            "Time tracking for hourly projects records billable hours automatically.",
            "Milestone billing releases partial payments on approved deliverables.",
            "Dispute resolution team mediates unresolved client-freelancer conflicts.",
            "Reviews and ratings are posted after project completion.",
            "Skill tests verify freelancer expertise in specific technologies.",
            "Subscription tiers give freelancers visibility boosts and reduced commissions.",
            "Project categories include development, design, writing, and marketing.",
            "Analytics show client lifetime value, repeat hire rate, and satisfaction scores.",
        ],
        "nfr": "Escrow PCI-DSS Level 2 compliance. Identity verification via government ID. GDPR for user data. Platform fee 10-20% tiered by relationship.",
    },
    {
        "domain": "job_board",
        "title": "Job Board and Career Platform",
        "overview": "An online job platform connecting employers with job seekers through listings and applications.",
        "all_features": [
            "Employers post job listings with salary range, requirements, and location.",
            "Job seekers search by title, location, experience level, and salary.",
            "Candidates apply with resume, cover letter, and screening questions.",
            "Applicant tracking shows employers the pipeline from applied to hired.",
            "Employer branding pages display company culture and open roles.",
            "Email and push notifications alert candidates to new matched jobs.",
            "Resume builder helps candidates create professional CVs within the platform.",
            "Salary benchmarking data shows industry-standard pay ranges per role.",
            "Recruiters can source candidates directly using search filters.",
            "Video interview scheduling integrates directly with Google Meet and Zoom.",
            "Job alerts send daily digests of new postings matching saved searches.",
            "Premium listings boost visibility to the top of search results.",
            "Diversity filters help employers reach underrepresented candidate pools.",
            "Hiring analytics show time-to-fill and source effectiveness per role.",
        ],
        "nfr": "GDPR right-to-erasure for candidate profiles. Search index refreshed every 60 seconds. 99.9% uptime. CDN for static assets.",
    },
    {
        "domain": "farm_management",
        "title": "Farm Management and Precision Agriculture Platform",
        "overview": "A platform for managing farm operations, crop planning, and IoT sensor integration.",
        "all_features": [
            "Farmers register fields with GPS boundaries and soil type data.",
            "Crop plans assign seed variety, planting dates, and expected yield per field.",
            "IoT soil sensors stream moisture and nutrient data to the dashboard.",
            "Weather integration shows forecasts and historical rainfall per farm zone.",
            "Irrigation schedules are automated based on soil moisture thresholds.",
            "Pesticide and fertilizer applications are logged with product and quantity.",
            "Harvest records capture yield per field and compare against forecasts.",
            "Expense tracking records input costs per crop season.",
            "Market price feeds show current commodity prices for planning sales.",
            "Livestock inventory tracks animal health records, vaccinations, and feed logs.",
            "Labour scheduling assigns field workers to tasks with time tracking.",
            "Drone imagery integration maps crop health via NDVI analysis.",
            "Government subsidy applications are tracked with deadline reminders.",
            "Seasonal profit and loss reports compare revenue against input costs.",
        ],
        "nfr": "IoT data ingestion at 10,000 events per second. Offline-capable mobile app for remote fields. GDPR for farm location data. REST API for integrations.",
    },
    {
        "domain": "nonprofit_management",
        "title": "Nonprofit Organization Management Platform",
        "overview": "A platform for managing donations, volunteers, programs, and reporting for nonprofits.",
        "all_features": [
            "Donors can make one-time or recurring donations through a secure portal.",
            "Tax receipt emails are automatically sent after each donation.",
            "Fundraising campaigns have goals, progress bars, and donor walls.",
            "Volunteer management handles recruitment, onboarding, and shift scheduling.",
            "Program staff track beneficiary services delivered per project.",
            "Grant management records funding sources, deliverables, and deadlines.",
            "Expense tracking categorizes spending against program and overhead budgets.",
            "Board members access financial reports and governance documents.",
            "Event registration handles ticketed and free events with attendance tracking.",
            "Email campaigns engage donors with impact stories and appeals.",
            "Impact metrics track beneficiaries served, outcomes, and reach by program.",
            "Donor relationship management records interactions and giving history.",
            "Annual impact reports are generated from aggregated program data.",
            "Volunteer hour logs produce community service certificates automatically.",
        ],
        "nfr": "PCI-DSS for donation processing. IRS Form 990 data exports. GDPR for donor and beneficiary data. 99.9% uptime during fundraising campaigns.",
    },
    {
        "domain": "property_rental",
        "title": "Property Rental Management Platform",
        "overview": "A platform for landlords and tenants to manage rental listings, leases, and payments.",
        "all_features": [
            "Landlords list properties with photos, rent, and availability dates.",
            "Tenants search listings by location, price, and bedroom count.",
            "Rental applications are submitted with income verification documents.",
            "Background and credit checks are initiated for shortlisted applicants.",
            "Lease agreements are generated and signed electronically.",
            "Monthly rent is collected via automated direct debit.",
            "Maintenance requests are submitted by tenants and tracked to resolution.",
            "Move-in and move-out inspection reports are completed with photos.",
            "Security deposit accounting tracks holding and deduction details.",
            "Landlord dashboards show occupancy rates, income, and expense summaries.",
            "Late rent reminders and penalty notices are sent automatically.",
            "Utility billing integrations split shared utilities between tenants.",
            "Landlord financial reports export annual income for tax filing.",
            "Tenant portal provides lease documents, payment history, and request status.",
        ],
        "nfr": "GDPR for tenant personal and financial data. Electronic signatures legally binding in supported jurisdictions. PCI-DSS for payment processing.",
    },
    {
        "domain": "food_delivery",
        "title": "Food Delivery and Restaurant Aggregator Platform",
        "overview": "A delivery platform aggregating restaurant menus and coordinating customer orders with delivery.",
        "all_features": [
            "Customers browse nearby restaurant menus with delivery time estimates.",
            "Customizable order options handle modifiers like toppings and portion sizes.",
            "Cart management supports orders from a single restaurant per checkout.",
            "Payment processing accepts cards, wallets, and cash-on-delivery.",
            "Order confirmation is sent to customer and restaurant simultaneously.",
            "Restaurant kitchen display shows incoming orders with preparation timers.",
            "Delivery drivers are assigned based on proximity and availability.",
            "Real-time delivery tracking shows driver position on customer's map.",
            "Rating and review system collects feedback on food and delivery.",
            "Promotional codes and loyalty cashback are applied during checkout.",
            "Scheduled orders are accepted up to 24 hours in advance.",
            "Restaurant dashboard shows sales analytics, order volume, and ratings.",
            "Customer service chat handles complaints and refund escalations.",
            "Peak-hour surge fees are applied transparently with customer notice.",
        ],
        "nfr": "Order-to-confirmation under 5 seconds. GPS updates every 10 seconds. Handle 100,000 concurrent orders. PCI-DSS. GDPR for customer location data.",
    },
    {
        "domain": "spa_salon",
        "title": "Spa and Beauty Salon Management System",
        "overview": "A booking and management platform for spas and beauty salons.",
        "all_features": [
            "Clients book appointments for services by selecting therapist and time.",
            "Service menu is configured with duration, price, and staff availability.",
            "Online deposit payment confirms appointments and reduces no-shows.",
            "Automated reminders are sent 24 hours and 1 hour before appointments.",
            "Staff schedules are managed with shift templates and time-off requests.",
            "Client profiles store treatment history, preferences, and allergies.",
            "Loyalty points are awarded per visit and redeemable for discounts.",
            "Point-of-sale handles walk-in payments and product retail sales.",
            "Gift vouchers are sold online and redeemed at checkout.",
            "Commission tracking calculates therapist earnings per service performed.",
            "Inventory tracks product stock with restocking alerts.",
            "Customer feedback surveys are sent after appointments.",
            "Revenue reports break down income by service category and staff member.",
            "Waiting-list management fills canceled slots automatically.",
        ],
        "nfr": "PCI-DSS for payment processing. GDPR for client health records. Booking confirmation under 1 second. SMS and email notifications.",
    },
    {
        "domain": "charity_donations",
        "title": "Online Charity and Donation Management Platform",
        "overview": "A platform for charity fundraising, donor management, and gift aid processing.",
        "all_features": [
            "Donors make one-time or recurring donations to charity campaigns.",
            "Gift Aid declarations are collected for eligible taxpayers.",
            "Fundraising pages allow individuals to raise money on behalf of the charity.",
            "Peer-to-peer fundraising tracks team and individual totals.",
            "Donation receipts include charity registration and tax reference numbers.",
            "Donor communication includes thank-you emails and impact updates.",
            "Campaign progress meters display total raised versus goal.",
            "Corporate matching requests are submitted and tracked.",
            "Donation form embeds allow integration into third-party websites.",
            "Refund requests are processed within charity governance policies.",
            "Donor database records interaction history and giving patterns.",
            "Legacy pledges are recorded and managed separately from cash donations.",
            "Annual donor statements are generated for tax purposes.",
            "Charity regulator reporting exports aggregate donation data.",
        ],
        "nfr": "PCI-DSS Level 1 for card processing. GDPR for donor data. Charity Commission compliance. 99.9% donation portal uptime.",
    },
    {
        "domain": "subscription_box",
        "title": "Subscription Box E-Commerce Platform",
        "overview": "A platform for managing subscription box products, recurring billing, and fulfillment.",
        "all_features": [
            "Customers subscribe to monthly box plans with customization options.",
            "Recurring billing charges subscribers automatically on renewal dates.",
            "Subscribers manage preferences to personalize box contents.",
            "Warehouse staff receive packing lists matched to subscriber preferences.",
            "Shipping labels are generated and tracking numbers sent to customers.",
            "Pause and cancel options are managed with win-back retention flows.",
            "Skip-month requests adjust billing and packing for the next cycle.",
            "Referral codes reward subscribers for bringing new customers.",
            "Product suppliers submit inventory availability for box curation.",
            "Curation team assigns products to subscription tiers for each cycle.",
            "Customer service handles damaged item replacements and substitution requests.",
            "Revenue dashboards show monthly recurring revenue, churn rate, and average order value.",
            "Product reviews from subscribers guide future curation decisions.",
            "Subscriber lifecycle analytics track cohort retention over 12 months.",
        ],
        "nfr": "PCI-DSS for recurring billing. GDPR for subscriber data. Batch shipping label generation for 10,000 orders within 1 hour. 99.9% uptime.",
    },
    {
        "domain": "waste_management",
        "title": "Waste Collection and Recycling Management System",
        "overview": "A smart waste management platform for municipalities to optimize collection routes and recycling.",
        "all_features": [
            "Residents report overflowing bins and illegal dumping via mobile app.",
            "Collection routes are optimized daily based on bin fill levels.",
            "IoT bin sensors report fill percentage to the operations dashboard.",
            "Collection vehicles track GPS routes and report completion per stop.",
            "Recycling sorting facilities record material intake and contamination rates.",
            "Residents receive collection schedule notifications for different waste types.",
            "Commercial waste accounts manage subscription collection services.",
            "Billing generates invoices for commercial collection based on bin size.",
            "Violation notices are issued for improper waste disposal.",
            "Recycling incentive programs reward households for sorted recyclables.",
            "Fleet maintenance schedules track vehicle service due dates.",
            "Environmental reports calculate diversion rates and carbon footprint.",
            "Complaints are logged and resolved with SLA tracking.",
            "Annual recycling performance reports are submitted to regulators.",
        ],
        "nfr": "IoT data ingestion at 5,000 events per second. Route optimization under 10 seconds for 500 vehicles. GDPR for household data. Offline mobile for drivers.",
    },
    {
        "domain": "energy_monitoring",
        "title": "Energy Monitoring and Utility Management Platform",
        "overview": "A platform for monitoring energy consumption, managing utilities, and identifying savings opportunities.",
        "all_features": [
            "Smart meters report electricity, gas, and water consumption in real time.",
            "Consumption dashboards show usage by hour, day, and month.",
            "Automated billing generates invoices based on meter readings.",
            "Anomaly detection flags unusually high consumption for investigation.",
            "Energy benchmarking compares consumption against similar buildings.",
            "Tariff management supports multiple rate plans and time-of-use pricing.",
            "Tenant sub-metering tracks individual unit consumption in multi-tenanted buildings.",
            "Renewable energy generation from solar panels is tracked and net-metered.",
            "Demand response events notify subscribers to reduce consumption during peaks.",
            "Maintenance alerts are triggered for faulty meters or broken sensors.",
            "Carbon footprint calculations convert consumption to CO2 equivalent.",
            "Budget tracking compares actual utility spend against forecasts.",
            "Regulator reports export consumption data in standard meter data formats.",
            "Portfolio dashboard manages energy data across multiple sites.",
        ],
        "nfr": "Meter data ingestion at 1,000 readings per second. GDPR for consumption data. API compliant with ESPI/Green Button standard. 99.9% uptime.",
    },
    {
        "domain": "school_management",
        "title": "K-12 School Management Information System",
        "overview": "A comprehensive MIS for schools to manage student records, timetables, and parent communication.",
        "all_features": [
            "Students are enrolled with personal details, class assignment, and medical notes.",
            "Timetable scheduling assigns teachers, rooms, and subjects per period.",
            "Attendance is recorded by teachers each class and reported to parents.",
            "Gradebook tracks continuous assessment and exam marks per subject.",
            "Parent portal allows viewing of attendance, grades, and announcements.",
            "Report cards are generated each term and accessible through the portal.",
            "Behavioural incidents are logged with actions taken and parent notification.",
            "Library management tracks book loans and overdue returns.",
            "Fee collection handles tuition billing, receipts, and arrears tracking.",
            "School calendar publishes events, holidays, and exam schedules.",
            "Staff leave management processes applications and tracks balances.",
            "Canteen management tracks meal selections and daily payments.",
            "Annual school census data is exported for ministry submissions.",
            "Special educational needs profiles track support plans and reviews.",
        ],
        "nfr": "FERPA/GDPR for student records. Accessible to parents via mobile. Timetable generation under 30 seconds. 99.9% uptime during term.",
    },
    {
        "domain": "airport_operations",
        "title": "Airport Operations Management System",
        "overview": "A platform for coordinating gate assignments, ground handling, and passenger operations at airports.",
        "all_features": [
            "Flight schedules are imported from airlines and displayed on operations boards.",
            "Gate assignments are made based on aircraft size and terminal logistics.",
            "Ground handling teams receive task assignments for each arriving and departing flight.",
            "Baggage tracking follows bags from check-in through sorting to loading.",
            "Aircraft turnaround timers track each ground service against schedule.",
            "Passenger boarding passes are scanned at gates for head count.",
            "Security lane staffing is adjusted based on passenger volume forecasts.",
            "Lounge access control verifies passenger eligibility at entry.",
            "Retail and food concession sales are tracked for revenue share.",
            "Incident reports log airside events with response coordination.",
            "Delay notifications are pushed to passengers with revised boarding times.",
            "Resource scheduler manages ground equipment allocation per flight.",
            "Runway and taxiway occupancy is monitored for safety compliance.",
            "Performance reports show on-time departure rates and turnaround times.",
        ],
        "nfr": "Real-time data integration with AODB and FIDS systems. ICAO standard messaging. System response under 500ms. 99.99% uptime for safety-critical functions.",
    },
    {
        "domain": "legal_billing",
        "title": "Legal Billing and Time Tracking System",
        "overview": "A time-tracking and billing platform for law firms to manage client invoicing and trust accounts.",
        "all_features": [
            "Attorneys record billable time entries against client matters.",
            "Expense disbursements are logged and allocated to client accounts.",
            "Client invoices are generated from approved time and expense entries.",
            "Trust account management tracks client funds held in escrow.",
            "Electronic billing submissions are formatted to LEDES standards.",
            "Write-off requests require partner approval before reducing invoiced amounts.",
            "Credit notes and payment allocations adjust client balances.",
            "Collections aging report shows overdue invoice amounts by client.",
            "Budget tracking alerts attorneys when a matter approaches its fee cap.",
            "Retainer replenishment requests are auto-triggered when trust balance is low.",
            "Partner dashboards show billable hour targets and realization rates.",
            "Revenue reports break down billings by practice group and client.",
            "Conflict-of-interest checks are run when opening new client matters.",
            "Audit trail logs all time entry modifications for compliance review.",
        ],
        "nfr": "ABA Model Rules compliance for trust accounting. LEDES 1998B format for e-billing. Encryption for client financial data. SOC 2 Type II certification.",
    },
    {
        "domain": "construction_pm",
        "title": "Construction Project Management Platform",
        "overview": "A project management platform for tracking construction projects, subcontractors, and site safety.",
        "all_features": [
            "Project managers create projects with scope, budget, and milestone schedule.",
            "Subcontractors are onboarded with licenses, insurance certificates, and contacts.",
            "Daily site reports capture work completed, resources used, and issues.",
            "Drawing and document management version-controls all project drawings.",
            "Requests for information are submitted and tracked to resolution.",
            "Submittals for materials and equipment are reviewed and approved.",
            "Budget tracking compares contract values against actual cost commitments.",
            "Change orders are documented, priced, and approved by the owner.",
            "Punch list items are assigned and tracked to completion before handover.",
            "Safety inspections are conducted digitally with photo evidence.",
            "Incident reports log near-misses and accidents with corrective actions.",
            "Labour hour tracking records workers onsite per trade per day.",
            "Project schedule is updated from baseline with variance analysis.",
            "Defect liability period tracking manages post-completion warranty claims.",
        ],
        "nfr": "Large drawing file support up to 500MB per file. Mobile offline capability for site use. ISO 19650 BIM compliance. GDPR for worker personal data.",
    },
    {
        "domain": "social_welfare",
        "title": "Social Welfare Case Management System",
        "overview": "A case management system for social workers to manage client assessments, plans, and services.",
        "all_features": [
            "Social workers create client cases with demographic and risk assessment data.",
            "Needs assessments are completed digitally with standardized questionnaires.",
            "Service plans define goals, interventions, and review dates.",
            "Referrals to partner agencies are sent and tracked for follow-up.",
            "Case notes record all client contacts and home visit outcomes.",
            "Child protection plans are managed with statutory review workflows.",
            "Court-ordered supervision requirements are tracked with compliance alerts.",
            "Benefit entitlements are calculated and applications submitted from the system.",
            "Crisis interventions are logged with escalation to emergency services.",
            "Supervisor review queues approve risk-level changes and plan closures.",
            "Outcome measures track family and individual progress against service plans.",
            "Multi-agency meetings are scheduled with shared agenda and minutes.",
            "Anonymous reporting allows referrals from public or professionals.",
            "Annual caseload reports inform workforce planning and funding applications.",
        ],
        "nfr": "Role-based access control with audit logs. GDPR sensitive data handling. Data residency within jurisdiction. 99.9% uptime for statutory services.",
    },
    {
        "domain": "sports_club",
        "title": "Sports Club Membership and Facility Management",
        "overview": "A management platform for sports clubs to handle memberships, bookings, and league scheduling.",
        "all_features": [
            "Members register and purchase annual or seasonal membership plans.",
            "Facility slots such as courts, pitches, and lanes are bookable through the member portal.",
            "Coaches manage team rosters, training schedules, and match availability.",
            "League fixtures are generated and results recorded after each match.",
            "Standings tables and statistics are updated automatically after results.",
            "Equipment hire is bookable at the front desk or online.",
            "Junior section parents track their child's attendance and development.",
            "Membership renewal reminders are sent 30 days before expiry.",
            "Event management handles club tournaments, social events, and guest bookings.",
            "Online shop sells club merchandise and equipment.",
            "Finance reports track membership income and facility revenue.",
            "Volunteer coordination assigns officials and helpers for events.",
            "Coaching certifications are tracked with renewal reminders.",
            "Annual report compiles membership, activity, and financial summary.",
        ],
        "nfr": "PCI-DSS for membership payments. GDPR for member data including minors. Booking confirmation under 1 second. Mobile-friendly portal.",
    },
]

ALL_DOMAINS = DOMAINS + EXTENDED_DOMAINS


_SIZE_COUNTS = {"small": 3, "medium": 5, "large": 8, "xl": 11, "2xl": 14}


def _get_features_for_size(domain_data: dict, size: str) -> list[str] | None:
    legacy_key = f"features_{size}"
    if legacy_key in domain_data:
        return domain_data[legacy_key]
    if "all_features" in domain_data:
        n = _SIZE_COUNTS.get(size, 5)
        features = domain_data["all_features"]
        if len(features) >= n:
            return features[:n]
    return None


def _build_brief_text(domain_data: dict, size: str) -> str:
    features = _get_features_for_size(domain_data, size)
    if not features:
        return ""
    feature_block = "\n".join(f"- {f}" for f in features)
    return textwrap.dedent(f"""
        Project Title:
        {domain_data['title']}

        Project Overview:
        {domain_data['overview']}

        Main Features:
        {feature_block}

        Non-Functional Requirements:
        {domain_data['nfr']}
    """).strip()


def _run_pipeline_on_text(text: str) -> tuple[object, object] | None:
    """
    Run rule-based pipeline on brief text.
    Returns (task_list, critic_report) or None on failure.
    """
    llm = FallbackOnlyClient()
    planner = PlannerAgent(llm)  # type: ignore[arg-type]

    try:
        parser = BriefParser()
        reqs = parser.parse(text)
    except BriefValidationError:
        # try treating as inline requirements
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("Project")]
        if not lines:
            return None
        reqs = [
            RequirementItem(line_no=i + 1, source=f"line {i + 1}", text=ln)
            for i, ln in enumerate(lines)
        ]

    if not reqs:
        return None

    req_text = "\n".join(f"[{r.source}] {r.text}" for r in reqs)
    planner._last_prepared_requirements = list(reqs)
    planner._prepare_requirements = lambda _t, force_fallback=False: (req_text, list(reqs))  # type: ignore[method-assign]

    try:
        task_list = planner.plan_from_requirements(
            req_text,
            allow_fallback=True,
            allow_decomposition=True,
            force_fallback=True,
        )
        task_list = EffortEstimator.enrich_task_list(task_list)
        critic = CriticAgent()
        report = critic.review(task_list)
        return task_list, report
    except Exception:
        return None


def _prompt_for_brief(text: str) -> str:
    """Reconstruct the LLM prompt that the planner would send (without KB context)."""
    try:
        reqs = BriefParser().parse(text)
    except BriefValidationError:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        reqs = [RequirementItem(line_no=i + 1, source=f"line {i + 1}", text=ln) for i, ln in enumerate(lines)]

    req_text = "\n".join(f"[{r.source}] {r.text}" for r in reqs)
    return req_text


def _to_training_pair(
    brief_text: str,
    task_list: object,
    source_label: str,
) -> dict:
    """Convert a (brief, task_list) pair to a chat-format training example."""
    from src.agents.planner import PlannerAgent as _P
    system_prompt = (
        "You are a senior software project planner. "
        "Analyze the software requirements and produce a structured project plan as JSON. "
        "Output ONLY valid JSON with a top-level 'tasks' array. "
        "Each task must have: id (T001...), title, description, req_type (FR/NFR), "
        "complexity (1-5), dependencies (list of task IDs), source (line reference)."
    )

    user_content = _prompt_for_brief(brief_text)

    import json as _json
    assistant_content = _json.dumps(
        task_list.model_dump(mode="json"),  # type: ignore[attr-defined]
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return {
        "source": source_label,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
    }


def _source_family(source_label: str) -> str:
    parts = source_label.split(":")
    if len(parts) >= 3:
        return ":".join(parts[:2])
    return source_label


def _stable_family_order(source_label: str) -> str:
    digest = hashlib.sha1(source_label.encode("utf-8")).hexdigest()
    return f"{digest}:{source_label}"


def _pick_holdout_families(
    grouped_pairs: list[tuple[str, list[dict]]],
    target_pair_count: int,
) -> set[str]:
    if target_pair_count <= 0:
        return set()
    selected: set[str] = set()
    selected_count = 0
    for family, family_pairs in grouped_pairs:
        if selected and selected_count >= target_pair_count:
            break
        selected.add(family)
        selected_count += len(family_pairs)
    return selected


def _split_pairs_by_family(
    pairs: list[dict],
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> dict:
    if val_ratio < 0 or test_ratio < 0 or (val_ratio + test_ratio) >= 1:
        raise ValueError("val_ratio and test_ratio must be >= 0 and sum to less than 1.")

    grouped: dict[str, list[dict]] = {}
    for pair in pairs:
        family = _source_family(str(pair.get("source", "unknown")))
        grouped.setdefault(family, []).append(pair)

    grouped_items = sorted(grouped.items(), key=lambda item: _stable_family_order(item[0]))
    total_pairs = len(pairs)
    target_test = round(total_pairs * test_ratio)
    target_val = round(total_pairs * val_ratio)

    test_families = _pick_holdout_families(grouped_items, target_test)
    remaining_items = [
        (family, items)
        for family, items in grouped_items
        if family not in test_families
    ]
    val_families = _pick_holdout_families(remaining_items, target_val)

    train_pairs: list[dict] = []
    val_pairs: list[dict] = []
    test_pairs: list[dict] = []
    for family, family_pairs in grouped_items:
        if family in test_families:
            test_pairs.extend(family_pairs)
        elif family in val_families:
            val_pairs.extend(family_pairs)
        else:
            train_pairs.extend(family_pairs)

    return {
        "train": train_pairs,
        "val": val_pairs,
        "test": test_pairs,
        "train_families": sorted({_source_family(pair["source"]) for pair in train_pairs}),
        "val_families": sorted(val_families),
        "test_families": sorted(test_families),
        "strategy": "deterministic_family_holdout",
    }


def build_dataset(
    max_synthetic: int = 300,
    min_score: float = 0.70,
    min_tasks: int = 3,
    max_tasks: int = 20,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pairs: list[dict] = []
    stats = {"total_attempted": 0, "passed": 0, "failed_pipeline": 0, "failed_score": 0, "failed_task_count": 0}

    # ── 1. Existing brief files ───────────────────────────────────────────
    print("[*] Processing existing brief files...")
    existing_brief_files = sorted(BRIEFS_DIR.glob("*.txt"))
    for brief_path in existing_brief_files:
        text = brief_path.read_text(encoding="utf-8")
        stats["total_attempted"] += 1
        result = _run_pipeline_on_text(text)
        if result is None:
            stats["failed_pipeline"] += 1
            print(f"  FAIL  {brief_path.name} -- pipeline failed")
            continue
        task_list, critic_report = result
        score = critic_report.score  # type: ignore[attr-defined]
        count = len(task_list.tasks)  # type: ignore[attr-defined]
        if score < min_score:
            stats["failed_score"] += 1
            print(f"  FAIL  {brief_path.name} -- score={score:.2f} (below {min_score})")
            continue
        if not (min_tasks <= count <= max_tasks):
            stats["failed_task_count"] += 1
            print(f"  FAIL  {brief_path.name} -- tasks={count} (out of range {min_tasks}-{max_tasks})")
            continue
        pairs.append(_to_training_pair(text, task_list, f"existing:{brief_path.name}"))
        stats["passed"] += 1
        print(f"  OK    {brief_path.name} -- score={score:.2f}, tasks={count}")

    # ── 2. Synthetic briefs ───────────────────────────────────────────────
    print(f"\n[*] Generating synthetic briefs (target: {max_synthetic})...")
    synthetic_generated = 0
    sizes = ["small", "medium", "large", "xl", "2xl"]

    for domain_data in ALL_DOMAINS:
        if synthetic_generated >= max_synthetic:
            break
        for size in sizes:
            if synthetic_generated >= max_synthetic:
                break
            text = _build_brief_text(domain_data, size)
            if not text:
                continue
            label = f"synthetic:{domain_data['domain']}:{size}"
            stats["total_attempted"] += 1
            result = _run_pipeline_on_text(text)
            if result is None:
                stats["failed_pipeline"] += 1
                print(f"  FAIL  {label} -- pipeline failed")
                continue
            task_list, critic_report = result
            score = critic_report.score  # type: ignore[attr-defined]
            count = len(task_list.tasks)  # type: ignore[attr-defined]
            if score < min_score:
                stats["failed_score"] += 1
                print(f"  FAIL  {label} -- score={score:.2f}")
                continue
            if not (min_tasks <= count <= max_tasks):
                stats["failed_task_count"] += 1
                print(f"  FAIL  {label} -- tasks={count}")
                continue
            pairs.append(_to_training_pair(text, task_list, label))
            stats["passed"] += 1
            synthetic_generated += 1
            print(f"  OK    {label} -- score={score:.2f}, tasks={count}")

    # ── 3. Save outputs ───────────────────────────────────────────────────
    print(f"\n[*] Saving {len(pairs)} training pairs...")

    # Full JSONL
    full_path = OUTPUT_DIR / "training_data.jsonl"
    with open(full_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    split_data = _split_pairs_by_family(
        pairs,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
    )
    train_pairs = split_data["train"]
    val_pairs = split_data["val"]
    test_pairs = split_data["test"]

    train_path = OUTPUT_DIR / "train.jsonl"
    val_path = OUTPUT_DIR / "val.jsonl"
    test_path = OUTPUT_DIR / "test.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for pair in train_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for pair in val_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    with open(test_path, "w", encoding="utf-8") as f:
        for pair in test_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    # Manifest
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_pairs": len(pairs),
        "train_pairs": len(train_pairs),
        "val_pairs": len(val_pairs),
        "test_pairs": len(test_pairs),
        "min_critic_score": min_score,
        "task_range": [min_tasks, max_tasks],
        "split_strategy": split_data["strategy"],
        "split_ratios": {
            "val_ratio": val_ratio,
            "test_ratio": test_ratio,
        },
        "families": {
            "train": split_data["train_families"],
            "val": split_data["val_families"],
            "test": split_data["test_families"],
        },
        "stats": stats,
        "files": {
            "full": str(full_path.relative_to(PROJECT_ROOT)),
            "train": str(train_path.relative_to(PROJECT_ROOT)),
            "val": str(val_path.relative_to(PROJECT_ROOT)),
            "test": str(test_path.relative_to(PROJECT_ROOT)),
        },
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print("  DATASET BUILD COMPLETE")
    print("=" * 60)
    print(f"  Total attempted : {stats['total_attempted']}")
    print(f"  Passed          : {stats['passed']}")
    print(f"  Failed pipeline : {stats['failed_pipeline']}")
    print(f"  Failed score    : {stats['failed_score']}")
    print(f"  Failed count    : {stats['failed_task_count']}")
    print(f"  Train split     : {len(train_pairs)}")
    print(f"  Val split       : {len(val_pairs)}")
    print(f"  Test split      : {len(test_pairs)}")
    print(f"  Train families  : {len(split_data['train_families'])}")
    print(f"  Val families    : {len(split_data['val_families'])}")
    print(f"  Test families   : {len(split_data['test_families'])}")
    print(f"  Output dir      : {OUTPUT_DIR}")
    print("=" * 60)

    if len(pairs) < 100:
        print("\n[!]  WARNING: fewer than 100 pairs -- add more domain templates before QLoRA training.")
    elif len(pairs) < 200:
        print(f"\n[!]  NOTE: {len(pairs)} pairs collected. Acceptable for initial fine-tuning, but 300+ is better.")
    else:
        print(f"\n[OK] {len(pairs)} pairs -- sufficient for QLoRA fine-tuning.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build QLoRA training dataset.")
    parser.add_argument("--max-synthetic", type=int, default=300)
    parser.add_argument("--min-score", type=float, default=0.70)
    parser.add_argument("--min-tasks", type=int, default=3)
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--val-ratio", type=float, default=0.10)
    parser.add_argument("--test-ratio", type=float, default=0.10)
    args = parser.parse_args()
    build_dataset(
        max_synthetic=args.max_synthetic,
        min_score=args.min_score,
        min_tasks=args.min_tasks,
        max_tasks=args.max_tasks,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )


if __name__ == "__main__":
    main()
