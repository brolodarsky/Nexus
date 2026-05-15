---
description: Cross-references Activities List, Date Ideas, and People Data to generate a markdown itinerary.
---

# Workflow: Plan Activity (`/plan_activity`)

This workflow reduces the cognitive load of social planning by dynamically building itineraries based on your stored ideas and the preferences of the people involved.

## Steps

1. Understand Parameters:
   - Ask the user for specific parameters if not provided: Who is attending? What's the budget? How much time do we have? Any specific vibe requested?

2. Retrieve Context:
   - Read the relevant idea lists from the Vault:
     - `Vault/4. Playground/4.2. Romance & Partnership/Date Ideas` (if romantic).
     - `Vault/4. Playground/4.1. Social Life & Community/Activities List` (if general).
   - Read relevant preferences from `Vault/4. Playground/4.1. Social Life & Community/People Data` for anyone specifically attending to ensure dietary needs or interests align.

3. Incorporate Real-World Data (Optional):
   - If enabled and necessary, use web search to check for upcoming local events, weather for outdoor activities, or specific opening hours.

4. Draft Itinerary:
   - Synthesize the retrieved information into a structured Markdown itinerary.
   - Outline the time, location, approximate cost, and why it fits the attendees' preferences.
   
5. Present and File:
   - Present the drafted itinerary to the user.
   - Upon approval, append the itinerary to the appropriate active note (e.g., a specific Date Log or Social Club planning document) using proper `##` headings and checkboxes for preparation tasks.
