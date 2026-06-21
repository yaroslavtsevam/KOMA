from google.adk.agents import LlmAgent

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    from google.adk.tools import ToolContext

def exit_loop(tool_context: ToolContext) -> dict:
    """
    Signals that the validation succeeded and the LoopAgent can terminate.
    """
    tool_context.actions.escalate = True
    return {"status": "success", "message": "Critic approved the data and terminated the quality loop."}

critic_agent = LlmAgent(
    name="CriticAgent",
    model="gemini-2.5-flash",
    instruction="""
    You are the CriticAgent. Your job is to validate the structured JSON data stored in 'omd_json_data' 
    against the raw syllabus content in 'rpd_content'.
    
    Validation Checklist:
    1. Omissions: Are all competencies (ОК, ОПК, ПК codes) and their know/can/master descriptors fully extracted and placed in Table 2?
    2. Table 1 structure: Is Table 1 strictly topic-based, containing one row per topic from the curriculum schedule? Does each row correctly map the topic name to the developed competencies (joined by a semicolon under 'comp_code', e.g. "ПКос-1.7; ПКос-3.2") and its evaluation tools?
    3. Table 4 Activities: Does the 'activities' list contain all the lectures and practical lessons from the syllabus Table 4? Are their details (num, theme, hours, type, comp_code, eval_tool) fully populated?
    4. Mapped Questions: Does each activity row contain a comprehensive list of teacher questions? Are these questions also mapped to 'colloquium.sections' for rendering?
    5. Assessment completeness: Are the exam questions, credit questions, test variants, and tasks fully extracted?
    6. Accuracy: Ensure no text was hallucinated or mixed up.
    
    If everything is 100% complete and correct, CALL the 'exit_loop' tool immediately to terminate the verification loop.
    If there are any omissions, missing questions, or errors, do NOT call 'exit_loop'. Instead, provide a detailed 
    critique describing what is missing or incorrect. The AnalyzerAgent will read your feedback in the next loop 
    iteration and fix the data.
    """,
    tools=[exit_loop]
)
