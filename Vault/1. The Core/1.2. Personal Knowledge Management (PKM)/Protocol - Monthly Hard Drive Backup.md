---
aliases: [Hard Drive Backup, Monthly Backup Protocol, FreeFileSync Backup]
tags: [pkm, backup, workflow, automation]
type: tool
---

---
**Back to:** [[Table of Contents]]
---

This protocol outlines the process for running a monthly backup of the primary hard drive to an external storage device using FreeFileSync as a batch job.

## 1. Objective
Ensure data redundancy and protection against hardware failure by maintaining a current, automated backup of essential files.

## 2. Configuration
The backup is managed via **FreeFileSync** using a pre-configured batch file (`.ffs_batch`).

- **Software:** [FreeFileSync](https://freefilesync.org/)
- **Job Type:** Batch Job (automated execution)
- **Source:** Local Primary Drive
- **Destination:** External Backup Drives

## 3. Execution Procedure

### Step 1: Connect External Storage
Ensure the external hard drive(s) are connected to the laptop and recognized by the system.

### Step 2: Run the Batch Job
Locate and run the FreeFileSync batch job file. This is typically configured to run silently or with a summary report at the end.

1.  Open the directory containing your `.ffs_batch` files.
	1. C Drive to BackupDrive/Backups/CompBackup![[1. The Core/1.2. Personal Knowledge Management (PKM)/BatchRun_CDrive_to_MainBackup.ffs_batch]]
2.  Double-click the backup batch file (e.g., `MonthlyBackup.ffs_batch`).
3.  Monitor the progress in the FreeFileSync pop-up (if not running completely silent).

### Step 3: Verify Success
1.  Check the FreeFileSync log file or the summary window for any errors (e.g., "File in use," "Disk full").
2.  Optionally, spot-check the destination drive to ensure recent files have been copied.

## 4. Frequency
Perform this backup on the **1st of every month**.
