from google.adk.agents import LlmAgent
from tools.docling_parser_tool import docling_parser_tool

# We use gemini-2.5-flash as the default reasoning model
parser_agent = LlmAgent(
    name="ParserAgent",
    model="gemini-2.5-flash",
    instruction="""
    You are the ParserAgent. 
    Your sole task is to parse the PDF course syllabus using the 'docling_parser_tool'.
    Call this tool immediately (without any arguments, as it will automatically retrieve the correct target path from the session state) to convert the PDF into clean, structured Markdown and store it in the session state under 'rpd_content'.
    
    After successfully calling the tool, you MUST output the entire parsed Markdown text (the 'parsed_markdown' field returned by the tool) in its entirety. Do not summarize it and do not truncate it. It is critical that your final output contains the exact text of the parsed syllabus so that the next agent receives it as context.
    """,
    tools=[docling_parser_tool]
)
