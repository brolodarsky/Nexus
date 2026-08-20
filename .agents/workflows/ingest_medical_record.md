---
description: Parse and ingest raw medical records (PDF, XML, Images) into the Vault.
---

# Steps

1. Identify Format and Ingestion Pathway:
   - For PDF & Images: Direct user to the Docling web demo for high-fidelity table extraction; accept the exported markdown.
   - For HL7 CDA XML: Run the automated parser script in step 2.
   - For other formats: Evaluate text extraction options and confirm approach with user.

2. Ingest and Parse Data:
   - For XML files, run:
     ```bash
     .venv/Scripts/python.exe src/nexus/shared_tools/medical_xml_parser.py <path_to_xml> <output_directory>
     ```
     - Example: `.venv/Scripts/python.exe src/nexus/shared_tools/medical_xml_parser.py Vault/HealthData_SENSITIVE.xml "Vault/2. Health/2.5. Mom's Health Tracking/Mom_Lab_Work"`
   - Verify generated markdown for data completeness.

3. Standardize Note and Frontmatter:
   - Apply the `generate_obsidian_note` skill to ensure valid structure and YAML frontmatter:
     ```yaml
     ---
     aliases: ["Date - Report Name"]
     tags: [health, lab_work, patient_name]
     type: log
     date: YYYY-MM-DD
     ---
     ```
   - Standardize filename using convention `YYYY-MM-DD - Type - Extras.md` (e.g., `2026-04-07 - Clinical Summary - Encounters and Diagnoses.md`).

4. Update Patient Dashboard and Clean Up:
   - Open patient's `Health Summary.md` (e.g., `Health Summary.md` or `Mom's Health Summary.md`) and add a wiki-link to the new record under the relevant log section.
   - Prompt user for confirmation before deleting the raw source file (XML, PDF, or image) to prevent vault clutter.
