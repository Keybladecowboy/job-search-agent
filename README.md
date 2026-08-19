# Job Search Agent

A small project to (1) automate tailoring resumes/cover letters to job postings,
and (2) re-learn Python along the way.

## Roadmap

1. **Master profile** (current step) - a structured JSON file with everything
   about your experience, skills, and projects. This is the raw material
   every later step pulls from.
2. **Job source** - a script that fetches job postings from an API/feed
   (e.g. Adzuna, RemoteOK).
3. **Tailoring script** - sends a job posting + your profile to the Claude
   API, gets back a tailored resume section and cover letter draft.
4. **Tracking log** - appends each generated application to a CSV.
5. **Full workflow** - chain steps 2-4 into one command.

## Step 1: Master Profile

1. Copy the template:
   ```
   cp profile/master_profile.template.json profile/master_profile.json
   ```
2. Open `master_profile.json` and replace every `"REPLACE: ..."` value with
   your real information. Be generous - more raw detail (extra bullet
   points, extra projects) gives the tailoring script more to work with
   later. Nothing gets cut here; narrowing happens per-job in step 3.
3. Validate it:
   ```
   python scripts/load_profile.py
   ```
   This checks the file loads correctly and flags any fields you forgot
   to fill in.

## Notes

- `master_profile.json` (your real, filled-in file) contains personal info -
  keep it out of any public git repo. Only the `.template.json` file should
  be shared/committed.
- Each script in this project is written with comments explaining the
  Python concepts it uses, since part of the point is refreshing on those
  while building something real.
