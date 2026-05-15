---
description: Parse and ingest raw medical records (PDF, XML, Images) into the Vault
---

# Ingest Medical Record Workflow

This workflow processes raw medical data and properly formats and files it into the patient's Health Logs or Lab Work directories.

## Identify the Correct Tools

1. **For PDF & Images:** Explain to the user that they should use the **Docling web demo** for high-fidelity extraction of complex tables. Tell the user to upload the file to Docling online, export the result as Markdown, and provide it to you.
2. **For HL7 CDA XML:** If the user has provided a raw XML file or it's in the Vault, proceed to the next step to execute the automated python parser.
3. **For other formats:** Provide suggestions to user.

## Execute Automated XML Ingestion if needed.

1. Use `python tools/medical_xml_parser.py <path_to_xml> <output_directory>`
   - Example: To ingest into Mom's logs: `tools/medical_xml_parser.py Vault/HealthData_SENSITIVE.xml "Vault/2. Health/2.5. Mom's Health Tracking/Mom_Lab_Work"`
2. Verify that the markdown was generated successfully.

## Post-Processing

1. Validate the generated format. Ensure it includes standard Frontmatter:
   ```yaml
   ---
   aliases: ["Date - Report Name"]
   tags: [health, lab_work, patient_name]
   type: log
   date: YYYY-MM-DD
   ---
   ```
2. Standardize the File Name: All ingested labs, visits, and logs must follow a consistent naming convention: `YYYY-MM-DD - Type - Extras.md`. Rename the file if necessary.
   - Example: `2026-04-07 - Clinical Summary - Encounters and Diagnoses.md`
   - Example: `2025-12-11 - Bloodwork - CBC and Metabolic Panel.md`
3. DELETE the raw file. Once ingestion is successful and verified, use the command line to delete the original XML, PDF, or Image file to avoid clutter.
4. Check the patient's `Health Summary.md` (e.g. `Mom's Health Summary.md`) and provide an entry linking to the new lab work/logs.