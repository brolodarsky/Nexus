---
aliases: [App List Update, Software Inventory Protocol]
tags: [pkm, workflow, automation]
type: tool
---

---
**Back to:** [[Table of Contents]]
---

This protocol outlines the process for updating the [[Laptop App List]] to ensure the digital inventory remains current.

## 1. Objective
Keep an accurate record of all installed software on the laptop for security audits, recovery, and system maintenance.

## 2. Update Procedure

### Step 1: Generate the App List
Run the following PowerShell script to generate a new markdown file on your desktop:

```powershell
$header = "| App Name | Version | Publisher |`n| :--- | :--- | :--- |";
$apps = Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*, HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* |
    Where-Object { $_.DisplayName -ne $null } |
    Select-Object DisplayName, DisplayVersion, Publisher |
    Sort-Object DisplayName |
    ForEach-Object { "| $($_.DisplayName) | $($_.DisplayVersion) | $($_.Publisher) |" };
$header + "`n" + ($apps -join "`n") | Out-File "$home\Desktop\App List.md"
```

### Step 2: Update the Vault
1.  Open the newly generated `App List.md` on your desktop.
2.  Copy the table content.
3.  Open [[Laptop App List]] in section 6.1 Digital Inventory.
4.  Replace the existing table with the updated content.
5.  Check for any significant changes or duplicates (e.g., [[Investigating Duplicate Laptop Apps]]).

## 3. Frequency
Perform this audit monthly or after major software installations/removals.
