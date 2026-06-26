import os
import logging
import requests
import json

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

def docling_parser_tool(tool_context: ToolContext, pdf_path: str = "FTD.01_R_RPD_2022.pdf") -> dict:
    """
    Parses a PDF syllabus (RPD) using IBM Docling, converts it to Markdown,
    and stores the result in the session state under 'rpd_content'.
    """
    # Use dynamic path from state if present
    pdf_path = tool_context.state.get("pdf_path", pdf_path)
    output_markdown_path = tool_context.state.get("output_markdown_path")
    regenerate = tool_context.state.get("regenerate", False)

    # Check if the parsed markdown file already exists and regenerate is False
    if output_markdown_path and os.path.exists(output_markdown_path) and not regenerate:
        logger.info(f"Parsed Markdown already exists at {output_markdown_path} and regenerate=False. Loading from file...")
        try:
            with open(output_markdown_path, "r", encoding="utf-8") as f:
                markdown_content = f.read()
            tool_context.state["rpd_content"] = markdown_content
            return {
                "status": "success", 
                "message": "Successfully loaded parsed RPD from existing file",
                "char_count": len(markdown_content),
                "parsed_markdown": markdown_content
            }
        except Exception as e:
            logger.warning(f"Failed to read existing parsed markdown at {output_markdown_path}: {e}. Proceeding with fresh parsing...")

    logger.info(f"Starting Docling parsing on file: {pdf_path}")
    
    if not os.path.exists(pdf_path):
        # Check in the workspace directory just in case it is relative
        workspace_path = os.path.join(os.getcwd(), pdf_path)
        if os.path.exists(workspace_path):
            pdf_path = workspace_path
        else:
            msg = f"Syllabus file not found: {pdf_path}"
            logger.error(msg)
            return {"status": "error", "message": msg}
            
    try:
        docling_serve_url = os.environ.get("DOCLING_SERVE_URL", "http://docling-serve:5001")
        convert_url = f"{docling_serve_url.rstrip('/')}/v1/convert/file"
        
        logger.info(f"Sending PDF to docling-serve for parsing: {pdf_path} (URL: {convert_url})")
        
        with open(pdf_path, "rb") as f:
            files = {"files": (os.path.basename(pdf_path), f, "application/pdf")}
            data = {"options": json.dumps({"to_formats": ["md"]})}
            
            response = requests.post(convert_url, files=files, data=data, timeout=600)
            
        if response.status_code != 200:
            msg = f"Docling server returned error status {response.status_code}: {response.text}"
            logger.error(msg)
            return {"status": "error", "message": msg}
            
        result = response.json()
        document = result.get("document", {})
        markdown_content = document.get("md_content")
        
        if not markdown_content:
            error_msg = result.get("errors") or result.get("message") or "No markdown content returned by docling-serve"
            msg = f"Failed to get markdown content from docling-serve: {error_msg}"
            logger.error(msg)
            return {"status": "error", "message": msg}
        
        # Save to shared agent session state
        tool_context.state["rpd_content"] = markdown_content
        
        # Also write the parsed markdown to the processing folder
        if output_markdown_path:
            dir_name = os.path.dirname(output_markdown_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(output_markdown_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            logger.info(f"Saved parsed Markdown to {output_markdown_path}")
        
        logger.info(f"Docling successfully parsed {pdf_path} (length: {len(markdown_content)} chars).")
        return {
            "status": "success", 
            "message": f"Successfully parsed RPD and saved to session state",
            "char_count": len(markdown_content),
            "parsed_markdown": markdown_content
        }
    except Exception as e:
        msg = f"Failed to parse PDF using Docling: {str(e)}"
        logger.exception(msg)
        return {"status": "error", "message": msg}


def read_parsed_syllabus_tool(tool_context: ToolContext) -> str:
    """
    Returns the parsed syllabus Markdown content from the session state.
    """
    return tool_context.state.get("rpd_content", "No parsed syllabus content found in state.")

