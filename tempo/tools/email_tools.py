"""
Email tools for account signup verification via IMAP.

Provides tools for checking email inbox and extracting verification
links/codes from emails during automated account signup flows.
"""

import asyncio
import email
import imaplib
import os
import re
from email.header import decode_header
from typing import Any

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema


class CheckInboxTool(Tool):
    """Check email inbox and return recent messages."""
    
    name = "check_inbox"
    description = (
        "Return the most recent emails from the inbox with subject, sender, and timestamp. "
        "Optionally filter by subject pattern. Use this to find verification emails."
    )
    category = ToolCategory.NETWORK
    
    def __init__(
        self,
        imap_host: str = "imap.gmail.com",
        imap_port: int = 993,
        imap_password: str | None = None,
        agent_email: str | None = None,
    ):
        """
        Initialize the check inbox tool.
        
        Args:
            imap_host: IMAP server hostname
            imap_port: IMAP server port (default: 993 for SSL)
            imap_password: IMAP password (app password for Gmail)
            agent_email: Email address to check
        """
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_password = imap_password or os.getenv("TEMPO_IMAP_PASSWORD")
        self.agent_email = agent_email or os.getenv("TEMPO_AGENT_EMAIL")
    
    async def execute(
        self,
        max_emails: int = 20,
        subject_pattern: str = "",
        **kwargs,
    ) -> ToolResult:
        """
        Get recent emails from inbox.
        
        Args:
            max_emails: Maximum number of emails to return (default: 20)
            subject_pattern: Optional regex pattern to filter subjects
            
        Returns:
            ToolResult with list of recent emails
        """
        if not self.imap_password:
            return ToolResult(
                success=False,
                output="",
                error="IMAP password not configured. Set TEMPO_IMAP_PASSWORD environment variable.",
            )
        
        if not self.agent_email:
            return ToolResult(
                success=False,
                output="",
                error="Agent email not configured. Set TEMPO_AGENT_EMAIL environment variable.",
            )
        
        # Compile regex pattern if provided
        subject_regex = None
        if subject_pattern:
            try:
                subject_regex = re.compile(subject_pattern, re.IGNORECASE)
            except re.error as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid subject pattern: {e}",
                )
        
        try:
            # Connect to IMAP server and fetch emails
            emails_found = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._fetch_recent_emails(max_emails, subject_regex),
            )
            
            if not emails_found:
                return ToolResult(
                    success=True,
                    output="No emails found in inbox.",
                    metadata={"count": 0, "emails": []},
                )
            
            # Format output
            lines = [f"Found {len(emails_found)} email(s):\n"]
            for em in emails_found:
                lines.append(f"- ID: {em['id']}")
                lines.append(f"  Subject: {em['subject']}")
                lines.append(f"  From: {em['from']}")
                lines.append(f"  Date: {em['date']}")
                lines.append("")
            
            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={"count": len(emails_found), "emails": emails_found},
            )
                
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"IMAP error: {str(e)}",
            )
    
    def _fetch_recent_emails(
        self,
        max_emails: int,
        subject_regex: re.Pattern | None,
    ) -> list[dict[str, Any]]:
        """Fetch recent emails (runs in thread pool)."""
        mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        try:
            mail.login(self.agent_email, self.imap_password)
            mail.select("INBOX")
            
            # Search for ALL emails, get the most recent ones
            _, message_ids = mail.search(None, "ALL")
            
            all_ids = message_ids[0].split()
            # Get the most recent emails (last N)
            recent_ids = all_ids[-max_emails:] if len(all_ids) > max_emails else all_ids
            # Reverse to show newest first
            recent_ids = list(reversed(recent_ids))
            
            emails = []
            for msg_id in recent_ids:
                _, msg_data = mail.fetch(msg_id, "(RFC822.HEADER)")
                
                if not msg_data or not msg_data[0]:
                    continue
                
                raw_email = msg_data[0][1]
                if isinstance(raw_email, bytes):
                    msg = email.message_from_bytes(raw_email)
                else:
                    msg = email.message_from_string(raw_email)
                
                # Decode subject
                subject = ""
                raw_subject = msg.get("Subject", "")
                if raw_subject:
                    decoded_parts = decode_header(raw_subject)
                    subject = " ".join(
                        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                        for part, enc in decoded_parts
                    )
                
                # Check subject pattern if provided
                if subject_regex and not subject_regex.search(subject):
                    continue
                
                emails.append({
                    "id": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                    "subject": subject,
                    "from": msg.get("From", ""),
                    "date": msg.get("Date", ""),
                })
            
            return emails
        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "max_emails": {
                        "type": "integer",
                        "description": "Maximum number of recent emails to return (default: 20)",
                        "default": 20,
                    },
                    "subject_pattern": {
                        "type": "string",
                        "description": "Optional regex pattern to filter by subject",
                    },
                },
                "required": [],
            },
        )


class GetEmailContentTool(Tool):
    """Fetch email body and extract verification links/codes."""
    
    name = "get_email_content"
    description = (
        "Fetch full email content by message ID and extract verification links "
        "and codes. Returns the email body along with any detected verification URLs or codes."
    )
    category = ToolCategory.NETWORK
    
    # Common patterns for verification links and codes
    LINK_PATTERNS = [
        r'https?://[^\s<>"\']+(?:verify|confirm|activate|validate|token)[^\s<>"\']*',
        r'https?://[^\s<>"\']+\?[^\s<>"\']*(?:token|code|key)=[^\s<>"\']+',
    ]
    CODE_PATTERNS = [
        r'(?:code|pin|otp)\s*(?:is)?[:\s]+([A-Z0-9]{4,8})\b',  # "code is: ABC123" or "code: ABC123"
        r'(?:verification|confirm).+?([A-Z0-9]{6})\b',  # 6-digit code after "verification" or "confirm"
        r'(?:enter|use)\s+(?:this\s+)?(?:code\s+)?[:\s]*([A-Z0-9]{4,8})',  # "enter code ABC123"
        r'\b([0-9]{6})\b',  # Standalone 6-digit numeric code (very common)
    ]
    
    def __init__(
        self,
        imap_host: str = "imap.gmail.com",
        imap_port: int = 993,
        imap_password: str | None = None,
        agent_email: str | None = None,
    ):
        """
        Initialize the get email content tool.
        
        Args:
            imap_host: IMAP server hostname
            imap_port: IMAP server port
            imap_password: IMAP password
            agent_email: Email address to check
        """
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_password = imap_password or os.getenv("TEMPO_IMAP_PASSWORD")
        self.agent_email = agent_email or os.getenv("TEMPO_AGENT_EMAIL")
    
    async def execute(
        self,
        message_id: str,
    ) -> ToolResult:
        """
        Fetch email content and extract verification data.
        
        Args:
            message_id: Email message ID from check_inbox
            purpose: Why this tool is being called
            
        Returns:
            ToolResult with email body and extracted links/codes
        """
        if not self.imap_password:
            return ToolResult(
                success=False,
                output="",
                error="IMAP password not configured. Set TEMPO_IMAP_PASSWORD environment variable.",
            )
        
        if not self.agent_email:
            return ToolResult(
                success=False,
                output="",
                error="Agent email not configured. Set TEMPO_AGENT_EMAIL environment variable.",
            )
        
        if not message_id:
            return ToolResult(
                success=False,
                output="",
                error="message_id is required",
            )
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._fetch_email_content(message_id),
            )
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to fetch email: {str(e)}",
            )
    
    def _fetch_email_content(self, message_id: str) -> ToolResult:
        """Fetch email content (runs in thread pool)."""
        mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        try:
            mail.login(self.agent_email, self.imap_password)
            mail.select("INBOX")
            
            # Fetch full email
            _, msg_data = mail.fetch(message_id.encode(), "(RFC822)")
            
            if not msg_data or not msg_data[0]:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Email with ID {message_id} not found",
                )
            
            raw_email = msg_data[0][1]
            if isinstance(raw_email, bytes):
                msg = email.message_from_bytes(raw_email)
            else:
                msg = email.message_from_string(raw_email)
            
            # Extract body
            body = self._get_email_body(msg)
            
            # Extract verification links and codes
            verification_links = self._extract_links(body)
            verification_codes = self._extract_codes(body)
            
            # Format output
            lines = ["## Email Content\n"]
            lines.append(f"**Subject:** {msg.get('Subject', 'No subject')}")
            lines.append(f"**From:** {msg.get('From', 'Unknown')}")
            lines.append(f"**Date:** {msg.get('Date', 'Unknown')}\n")
            
            if verification_links:
                lines.append("### Verification Links Found")
                for link in verification_links:
                    lines.append(f"- {link}")
                lines.append("")
            
            if verification_codes:
                lines.append("### Verification Codes Found")
                for code in verification_codes:
                    lines.append(f"- `{code}`")
                lines.append("")
            
            lines.append("### Body\n")
            # Truncate very long bodies
            if len(body) > 5000:
                lines.append(body[:5000] + "\n\n[Truncated...]")
            else:
                lines.append(body)
            
            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={
                    "verification_links": verification_links,
                    "verification_codes": verification_codes,
                    "subject": msg.get("Subject", ""),
                    "from": msg.get("From", ""),
                },
            )
        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
    
    def _get_email_body(self, msg: email.message.Message) -> str:
        """Extract text body from email message."""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # Skip attachments
                if "attachment" in content_disposition:
                    continue
                
                # Prefer plain text, fall back to HTML
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                        break
                elif content_type == "text/html" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html = payload.decode(charset, errors="replace")
                        # Simple HTML to text conversion
                        body = self._html_to_text(html)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    body = self._html_to_text(body)
        
        return body.strip()
    
    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion."""
        # Remove script and style elements
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Replace common elements
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
        # Remove remaining tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    
    def _extract_links(self, text: str) -> list[str]:
        """Extract verification links from text."""
        links = []
        for pattern in self.LINK_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            links.extend(matches)
        # Deduplicate while preserving order
        seen = set()
        unique_links = []
        for link in links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        return unique_links[:10]  # Limit to 10 links
    
    def _extract_codes(self, text: str) -> list[str]:
        """Extract verification codes from text."""
        codes = []
        for pattern in self.CODE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            codes.extend(matches)
        # Deduplicate while preserving order
        seen = set()
        unique_codes = []
        for code in codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)
        return unique_codes[:5]  # Limit to 5 codes
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "Email message ID returned by check_inbox",
                    },
                },
                "required": ["message_id"],
            },
        )
