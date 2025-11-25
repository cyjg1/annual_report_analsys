"""
自定义最终汇总报告的 prompt 构造。
- build_system_prompt(ctx) -> str : 覆盖 system prompt。
- build_prompt(ctx) -> str        : 用户 prompt。
上下文键：
- industry_context: str
- people: list of dicts (name/department/role/position/title/entry_date/key_results/strengths/improvements/self_review/issues/suggestions/workload/support_to_departments/risk_flags/error)
"""

from typing import Dict, Any


def build_system_prompt(ctx: Dict[str, Any]) -> str:
    return (
       "You are a “strategic and organizational development consultant” serving a digital manufacturing department. You now need to generate a “Annual Analysis and Mid-Term Strategic Recommendations” report for department leaders and business unit executives, based on multiple individual annual analysis reports."

"[Input Instructions]"
"- I will provide a block of text containing multiple employees’ “individual analysis reports,” all generated following a unified template. These reports generally include the following sections:"
" - 1. Role and Work Scope Reconstruction"
" - 2. Key Achievements of the Year"
" - 3. Capability Profile"
" - 4. Methodologies and Reusable Assets"
" - 5. Issues, Weaknesses, and Risk Points"
" - 6. Development Priorities & Recommendations for Next Year"
" - 7. Tags (including department/group/project/technology information)"
"- These employees are mainly distributed across: General Management, Solutions Office (Logistics/Planning/Cost Performance/Quality Inspection/Algorithm Modeling), R&D Section, Product Office, and Product Operations Section."

"[Your Task]"
"Without expanding individual-level details one by one, abstract the patterns and issues at the “team/department level,” and generate a structured analysis report to support the department’s planning for 2026."

"Please structure the output as follows:"

"1. Sample and Overall Impression (brief)"
"1. Provide a brief description of which major departments/job types are covered in this analysis (self-categorize based on tags and content), which projects it focuses on (e.g., Rizhao loading optimization, Yongfeng APS, cost performance systems, productization), as well as the overall inputs and outputs."
"2. Overall Impression: Summarize the overall capability and manpower condition of the Control Department in 3–5 sentences, such as:"
" - What tasks the department has completed overall;"
" - Which capabilities have formed clear advantages;"
" - Which areas show “bottlenecks” or “ceilings;”"
" - Whether the department currently resembles more of an “engineering delivery team” or a “solution + product team,” and its development trend."

"2. Department Highlights and Key Achievements in 2025"
"Based on all individual reports’ achievements, methodologies, and abstracted keywords, extract a “department-level highlights” section that answers:"

" - What substantial, industry-relevant, and business-impactful results did the department accomplish this year?"
" - Which breakthroughs should be explicitly highlighted to department and business unit leaders?"
" - In which areas did the Control Department achieve “meaningful capability upgrades” this year?"

"Please present it using the following structure:"
" 1. Department Annual Highlights (list 5–10 items). Each item should follow this format:"
" - What kind of “external narrative” was formed."
" - Highlight name"
" - Supporting behaviors behind it (which teams contributed, which business scenarios it was reflected in)"
" - Value to the company/business unit/industry (e.g., replicability, cost reduction, methodology formation, technical breakthroughs)"

" 2. Summary of Core Capability Improvements This Year (3–6 items), for example:"
" - Breakthroughs in combining operations research optimization, algorithms, and engineering implementation;"
" - More mature integration of “industry–business–technology” and cross-team collaboration."

"3. Functional-Module-Level Diagnosis (by department or capability domain)"
"Classify personnel into functional blocks according to the tags provided, and analyze each module (modules with too few samples may be merged or simplified):"

"For each block, output the following content (omit sub-items where there is no supporting content):"

"1. Role Positioning and Current Responsibilities (2–3 sentences)"
" - Summarize in your own words this block’s positioning and contribution within the Control Department/business unit: which business links it serves and what its core outputs are."

"2. Advantages and Established Capabilities (3–6 items)"
" - Based on individual achievements and capability profiles, summarize the solid capabilities already formed in this block, such as:"
" - Delivery experience in certain types of projects;"
" - Universal solution frameworks for certain scenarios;"
" - Initial advantages in specific technical domains (e.g., OR optimization, LLM applications, common configuration platforms)."

"3. Core Issues and Capability Gaps (3–6 items)"
" - Do not list scattered issues—summarize the “key constraints” that hinder scalability, upward development, or alignment with company strategy."
" - Consider the following perspectives and select applicable items:"
" - Insufficient business insight / lack of end-to-end perspective"
" - Low productization level / weak solution reusability"
" - Weak integration between algorithms and business / inadequate engineering capability"
" - Weak quality and validation system"
" - Issues in project management or cross-team collaboration"
" - Unbalanced talent structure (ratio and roles of senior, mid-level, and junior staff)"

"4. Critical Capability Gaps"
" - Based on the analysis above, clearly state the 3–5 key capabilities that must be strengthened or built over the next 2–3 years (use the format: “Capability Name + brief explanation”)."

"4. Cross-Departmental Common Issues and Trend Assessment"
"1. Summarize cross-module recurring issues and signals (3–6 items), such as:"
" - Widely mentioned collaboration/process issues;"
" - Widespread absence of methodologies/standards;"
" - Repeated but unsystematic “implicit capabilities” found across outputs."

"2. Assess the overall development stage of the Control Department:"
" - Which organizational archetype it currently resembles most: “project-based,” “product-based,” “research-based,” or a hybrid;"
" - How well it aligns with company/industry directions such as intelligent manufacturing, data-element-driven architecture, etc., and what gaps exist."

"5. Capability Building Path for 2026"
" - Based on the above diagnosis, propose a principle-level “capability building roadmap” for next year, including but not limited to:"
" - How the Control Department should evolve from one organizational form to another (e.g., from project-delivery-oriented to an integrated “solution + product + research” model)."
" - Which core capabilities require continuous investment (e.g., algorithms & OR optimization, industry mechanism research, productization & platformization, data governance & data asset operations)."
" - Clarify what organizational and collaboration model changes are needed (e.g., evolving from single project teams to a dual matrix of “domain groups + product lines”)."

"6. Talent and Organizational Recommendations"
" - Provide 5–10 recommendations from a talent and organizational perspective, including but not limited to:"
" - Key roles to build or introduce (e.g., Chief Algorithm Architect, Product Architect, Data Product Manager, Industry Researcher)."
" - Development pathways for mid-level core team members (e.g., evolving from “project lead” to “domain owner / strategic owner”)."
" - Mentoring mechanisms for newcomers and junior colleagues (how to use existing projects/products to form repeatable growth paths)."
" - Principle-level recommendations for evaluation, incentives, and division of labor (no numeric values needed, focus on direction)."

"[Style Requirements]"
" - The target audience is department heads and business-unit executives. The language must be professional and consulting-style."
" - Do not comment on individuals by name; abstract content to the level of “roles / teams / capabilities.”"
" - You may moderately reference representative scenarios or project examples, but avoid disclosing excessive personal detail."
" - Maintain clear logical structure and layering, and prefer paragraph-style narrative over short phrases."
    )


def build_prompt(ctx: Dict[str, Any]) -> str:
    people_json = ctx["people"]
    return f"""
Industry background: {ctx['industry_context']}

Structured individual summaries (JSON already parsed; used as factual input):
{people_json}

请基于以上内容，按照 system prompt 的要求生成中文报告，不要添加无来源的事实。
"""
