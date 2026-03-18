---
aliases: [Automated Maintenance Tracker Project, Sheets Tracker Built]
tags: [auto, project, sheets, tracking]
type: plan
---

# Maintenance Tracker Game Plan

This document outlines the requirements and build steps for migrating the Honda Pilot service history into an automated, macro-driven Google Sheet.

## 🎯 Objective
Create a living, low-friction spreadsheet that not only logs past maintenance (cost, date, odometer) but proactively calculates when future maintenance is due based on standardized mileage intervals (e.g., Oil changes every 3,000 miles).

## 📋 Requirements
- **Inputs Required:** Date, Service Description, Current Odometer, Cost, Shop/Location.
- **Calculated Outputs:** 
  - `Next Service Odometer` (Current + Interval)
  - `Miles Until Due` (Next Service - Latest Logged Odometer)
- **Features:**
  - Conditional formatting (e.g., cell turns red when `Miles Until Due` < 500).
  - Clean, mobile-friendly interface (since inputs happen at the mechanic).

## 🪜 Implementation Steps
- [ ] **Phase 1: Structure & Schema**
  - [ ] Create the core `Log` tab with columns: Date | Odometer | Service | Notes | Cost.
  - [ ] Create a hidden/reference `Intervals` tab defining the rules (Oil = 3k, Tires = 10k, Trans Fluid = 30k).
- [ ] **Phase 2: Logic & Macros**
  - [ ] Build the `Dashboard` tab to query the `Log` and display "Current Status" of all major components.
  - [ ] Write Google AppScript (if necessary) or complex `VLOOKUP`/`MAXIFS` formulas to find the *most recent* service of each type and add the interval.
- [ ] **Phase 3: Polish**
  - [ ] Apply conditional formatting rules.
  - [ ] Test data entry on a mobile device.
  - [ ] Update the placeholder link in the [[Maintenance Log]] note to point to the live sheet.

## 🔗 Resources & Notes
*   *Link to AppScript documentation for sending email triggered reminders (if needed later).*
*   *Link to common Honda Pilot factory maintenance schedule thresholds.*

---
**Back to:** [[Table of Contents]]
