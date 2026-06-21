from google.adk.agents import LlmAgent
from tools.docx_generator_tool import docx_generator_tool

publisher_agent = LlmAgent(
    name="PublisherAgent",
    model="gemini-2.5-flash",
    instruction="""
    You are the PublisherAgent. Your sole job is to call the 'docx_generator_tool' to compile and 
    render the final Word report.
    
    It will load 'omd_json_data' from the session state, load the template, and generate the final OMD document.
    
    Call the 'docx_generator_tool' immediately (without any arguments, as it will automatically retrieve the correct target paths from the session state). Once completed, report that the OMD document has been generated.
    """,
    tools=[docx_generator_tool]
)
