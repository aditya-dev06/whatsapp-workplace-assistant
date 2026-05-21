import re

def format_for_whatsapp(text: str) -> str:
    """
    Converts standard Markdown formatting to WhatsApp-compatible markup.
    - Headers (# Header) -> *HEADER*
    - Bold (**bold**) -> *bold*
    - Italic (*italic* or _italic_) -> _italic_
    - Code blocks (```code```) -> ```code``` (retained)
    """
    if not text:
        return ""

    # 1. Translate Headers (# Header, ## Header, etc.)
    # Example: "### Leave Approved!" -> "*LEAVE APPROVED!*"
    def replace_header(match):
        header_text = match.group(2).strip().upper()
        return f"*{header_text}*"
    
    text = re.sub(r'^(#{1,6})\s+(.+)$', replace_header, text, flags=re.MULTILINE)

    # 2. Translate Bold (**bold** -> *bold*)
    # We must be careful not to conflict with already converted headers or standard asterisks.
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)

    # 3. Translate Italic (*italic* -> _italic_ if not part of bold asterisks)
    # We match single asterisks *italic* that are not adjacent to other asterisks
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'_\1_', text)

    # 4. Clean up any trailing space or double margins
    text = text.strip()
    
    return text
