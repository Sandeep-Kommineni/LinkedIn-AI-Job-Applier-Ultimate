"""HTML templates for creating resume sections"""

prompt_header_template = """
- **HTML Template**
```
<header>
  <h1>[Name and Surname]</h1>
  <div class="contact-info">
     <span>[City, Country]</span>
     <span class="sep">|</span>
     <span>[Open to Relocation / Remote]</span>
     <span class="sep">|</span>
     <span>[Your Prefix Phone number]</span>
     <span class="sep">|</span>
     <a href="mailto:[Your Email]">[Your Email]</a>
  </div>
  <div class="contact-links">
     <a href="[Link LinkedIn account]">[LinkedIn display URL]</a>
     <span class="sep">|</span>
     <a href="[Link GitHub Work account]">[GitHub Work display URL]</a>
     <span class="sep">|</span>
     <a href="[Link GitHub Personal account]">[GitHub Personal display URL]</a>
     <span class="sep">|</span>
     <a href="[Link Portfolio or Website]">[Portfolio display URL]</a>
  </div>
  <hr class="header-rule">
</header>
```
The results should be provided in html format, Provide only the html code for the resume, without any explanations or additional text and also without ```html ```
"""

prompt_education_template = """
- **HTML Template**
```
<section id="education">
    <h2>Education</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[University Name]</span>
          <span class="entry-location">[Location]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[Degree] in [Field of Study] | Grade: [Your Grade]</span>
          <span class="entry-year">[Start Year] – [End Year]  </span>
      </div>
    </div>
</section>
```
The results should be provided in html format, Provide only the html code for the resume, without any explanations or additional text and also without ```html ```
Provide the Grade only if it is strong and relevant.
"""


prompt_working_experience_template = """
- **HTML Template**
```
<section id="work-experience">
    <h2>Experience</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[Company Name] <span class="site-link"><a href="[Company URL]">[Company Domain]</a></span></span>
          <span class="entry-location">[Location]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[Your Job Title]</span>
          <span class="entry-year">[Start Date] – [End Date]</span>
      </div>
      <ul class="compact-list">
          <li>[Describe your responsibilities and achievements in this role] </li>
          <li>[Describe any key projects or technologies you worked with]</li>
          <li>[Mention any notable accomplishments or results]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[Company Name] <span class="site-link"><a href="[Company URL]">[Company Domain]</a></span></span>
          <span class="entry-location">[Location]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[Your Job Title]</span>
          <span class="entry-year">[Start Date] – [End Date] </span>
      </div>
      <ul class="compact-list">
          <li>[Describe your responsibilities and achievements in this role] </li>
          <li>[Describe any key projects or technologies you worked with]  </li>
          <li>[Mention any notable accomplishments or results]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[Company Name] <span class="site-link"><a href="[Company URL]">[Company Domain]</a></span></span>
          <span class="entry-location">[Location]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[Your Job Title]</span>
          <span class="entry-year">[Start Date] – [End Date] </span>
      </div>
      <ul class="compact-list">
          <li>[Describe your responsibilities and achievements in this role] </li>
          <li>[Describe any key projects or technologies you worked with]  </li>
          <li>[Mention any notable accomplishments or results]</li>
      </ul>
    </div>
</section>
```
The results should be provided in html format, Provide only the html code for the resume, without any explanations or additional text and also without ```html ```"""


prompt_side_projects_template = """
- **HTML Template**
```
<section id="side-projects">
    <h2>Projects</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[Project Name] — [Short one-line tagline describing the project] <span class="site-link"><a href="[Project URL]">[Site Domain]</a></span></span>
      </div>
      <ul class="compact-list">
          <li>[Describe any notable recognition or reception]</li>
          <li>[Describe any notable recognition or reception]</li>
          <li>[Describe any notable recognition or reception]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[Project Name] — [Short one-line tagline describing the project] <span class="site-link"><a href="[Project URL]">[Site Domain]</a></span></span>
      </div>
      <ul class="compact-list">
          <li>[Describe any notable recognition or reception]</li>
          <li>[Describe any notable recognition or reception]</li>
          <li>[Describe any notable recognition or reception]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[Project Name] — [Short one-line tagline describing the project] <span class="site-link"><a href="[Project URL]">[Site Domain]</a></span></span>
      </div>
      <ul class="compact-list">
          <li>[Describe any notable recognition or reception]</li>
          <li>[Describe any notable recognition or reception]</li>
          <li>[Describe any notable recognition or reception]</li>
      </ul>
    </div>
</section>
```
The results should be provided in html format, Provide only the html code for the resume, without any explanations or additional text and also without ```html ```
"""


prompt_achievements_template = """
- **HTML Template**
```
<section id="achievements">
    <h2>Achievements</h2>
    <ul class="compact-list">
      <li><strong>[Award or Recognition or Scholarship or Honor]:</strong> [Describe]</li>
      <li><strong>[Award or Recognition or Scholarship or Honor]:</strong> [Describe]</li>
      <li><strong>[Award or Recognition or Scholarship or Honor]:</strong> [Describe]</li>
    </ul>
</section>
```
The results should be provided in html format, Provide only the html code for the resume, without any explanations or additional text and also without ```html ```
"""

prompt_certifications_template = """
- **HTML Template**
```
<section id="certifications">
    <h2>Certifications</h2>
    <ul class="compact-list">
      <li><strong>[Certification Name]:</strong> [Describe]</li>
      <li><strong>[Certification Name]:</strong> [Describe]</li>
    </ul>
</section>
```
The results should be provided in html format, Provide only the html code for the resume, without any explanations or additional text and also without ```html ```
"""

prompt_additional_skills_template = """
- **HTML Template**
'''
<section id="skills-languages">
    <h2>Technical Skills</h2>
    <div class="two-column">
      <ul class="compact-list">
          <li><strong>AI/ML:</strong> [Skill], [Skill], [Skill], [Skill]</li>
          <li><strong>Languages:</strong> [Language], [Language], [Language]</li>
          <li><strong>Frameworks:</strong> [Framework], [Framework], [Framework]</li>
          <li><strong>Cloud & DevOps:</strong> [Skill], [Skill], [Skill]</li>
          <li><strong>Tools & Platforms:</strong> [Tool], [Tool], [Tool]</li>
          <li><strong>Databases:</strong> [DB], [DB]</li>
      </ul>
      <ul class="compact-list">
          <li><strong>Methodologies:</strong> [Method], [Method]</li>
          <li><strong>Soft Skills:</strong> [Skill], [Skill], [Skill]</li>
          <li><strong>Certifications:</strong> [Cert], [Cert]</li>
          <li><strong>Interests:</strong> [Interest], [Interest], [Interest]</li>
          <li><strong>Spoken Languages:</strong> [Language] ([Proficiency]), [Language] ([Proficiency])</li>
      </ul>
    </div>
</section>
'''

## Guidelines
- Include ALL skills from the provided skills list — do not omit any.
- Group related skills under bold category headers (e.g., **AI/ML:**, **Languages:**, **Frameworks:**).
- Tailor skill emphasis to the job description: prioritize skills that match the role requirements.
- Include spoken languages with proficiency levels at the end.
- If any category has no relevant skills, omit that line entirely.
- Use concise comma-separated lists within each category rather than one skill per bullet.

The results should be provided in html format, Provide only the html code for the resume, without any explanations or additional text and also without ```html ```
"""
