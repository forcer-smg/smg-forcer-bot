# -*- coding: utf-8 -*-
"""
Document Generator - Generate PDF, Word, and Excel documents
Supports templates, formatting, and dynamic content insertion
"""

import os
import logging
import re
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# PDF generation
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not available. PDF generation will be limited.")

# Word document generation
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not available. Word document generation will be limited.")

# Excel generation
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    logger.warning("openpyxl not available. Excel generation will be limited.")

# Markdown to HTML/PDF
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logger.warning("markdown not available. Markdown conversion will be limited.")


class DocumentGenerator:
    """Generate PDF, Word, and Excel documents with formatting and templates"""
    
    def __init__(self, output_dir: str = "generated_documents"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check availability
        self.pdf_available = REPORTLAB_AVAILABLE
        self.docx_available = DOCX_AVAILABLE
        self.xlsx_available = OPENPYXL_AVAILABLE
        self.markdown_available = MARKDOWN_AVAILABLE
        
        logger.info(f"Document Generator initialized - PDF: {self.pdf_available}, Word: {self.docx_available}, Excel: {self.xlsx_available}")
    
    def generate_pdf(self, 
                     content: Union[str, Dict],
                     filename: str = None,
                     title: str = None,
                     author: str = "SMG-Forcer Bot",
                     page_size: str = "letter",
                     **kwargs) -> Optional[str]:
        """
        Generate PDF document
        
        Args:
            content: Text content, markdown, or structured dict
            filename: Output filename (auto-generated if None)
            title: Document title
            author: Document author
            page_size: 'letter' or 'A4'
            **kwargs: Additional formatting options
        
        Returns:
            Path to generated PDF file or None if failed
        """
        if not self.pdf_available:
            logger.error("reportlab not available for PDF generation")
            return None
        
        try:
            # Generate filename if not provided
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"document_{timestamp}.pdf"
            
            if not filename.endswith('.pdf'):
                filename += '.pdf'
            
            filepath = self.output_dir / filename
            
            # Select page size
            size = A4 if page_size.upper() == 'A4' else letter
            
            # Create PDF document
            doc = SimpleDocTemplate(str(filepath), pagesize=size)
            story = []
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Add title
            if title:
                title_style = ParagraphStyle(
                    'CustomTitle',
                    parent=styles['Heading1'],
                    fontSize=24,
                    textColor=colors.HexColor('#1a1a1a'),
                    spaceAfter=30,
                    alignment=TA_CENTER
                )
                story.append(Paragraph(title, title_style))
                story.append(Spacer(1, 0.2*inch))
            
            # Process content
            if isinstance(content, dict):
                # Structured content
                story.extend(self._process_structured_content(content, styles))
            elif isinstance(content, str):
                # Text or markdown content
                if self.markdown_available and self._is_markdown(content):
                    # Convert markdown to HTML then to PDF
                    html_content = markdown.markdown(content, extensions=['extra', 'codehilite'])
                    story.extend(self._html_to_paragraphs(html_content, styles))
                else:
                    # Plain text
                    paragraphs = content.split('\n\n')
                    for para in paragraphs:
                        if para.strip():
                            story.append(Paragraph(para.strip(), styles['Normal']))
                            story.append(Spacer(1, 0.1*inch))
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"PDF generated: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error generating PDF: {e}", exc_info=True)
            return None
    
    def generate_word(self,
                     content: Union[str, Dict],
                     filename: str = None,
                     title: str = None,
                     **kwargs) -> Optional[str]:
        """
        Generate Word document (.docx)
        
        Args:
            content: Text content, markdown, or structured dict
            filename: Output filename (auto-generated if None)
            title: Document title
            **kwargs: Additional formatting options
        
        Returns:
            Path to generated Word file or None if failed
        """
        if not self.docx_available:
            logger.error("python-docx not available for Word generation")
            return None
        
        try:
            # Generate filename if not provided
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"document_{timestamp}.docx"
            
            if not filename.endswith('.docx'):
                filename += '.docx'
            
            filepath = self.output_dir / filename
            
            # Create document
            doc = Document()
            
            # Add title
            if title:
                title_para = doc.add_heading(title, 0)
                title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # Process content
            if isinstance(content, dict):
                self._add_structured_content_to_word(doc, content)
            elif isinstance(content, str):
                if self.markdown_available and self._is_markdown(content):
                    # Convert markdown to Word
                    self._markdown_to_word(doc, content)
                else:
                    # Plain text
                    paragraphs = content.split('\n\n')
                    for para in paragraphs:
                        if para.strip():
                            doc.add_paragraph(para.strip())
            
            # Save document
            doc.save(str(filepath))
            
            logger.info(f"Word document generated: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error generating Word document: {e}", exc_info=True)
            return None
    
    def generate_excel(self,
                      data: Union[List[List[Any]], Dict[str, List[List[Any]]]],
                      filename: str = None,
                      sheet_name: str = "Sheet1",
                      headers: List[str] = None,
                      **kwargs) -> Optional[str]:
        """
        Generate Excel spreadsheet (.xlsx)
        
        Args:
            data: List of rows (list of lists) or dict with sheet names as keys
            filename: Output filename (auto-generated if None)
            sheet_name: Name for single sheet (if data is list)
            headers: Column headers (optional)
            **kwargs: Additional formatting options
        
        Returns:
            Path to generated Excel file or None if failed
        """
        if not self.xlsx_available:
            logger.error("openpyxl not available for Excel generation")
            return None
        
        try:
            # Generate filename if not provided
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"spreadsheet_{timestamp}.xlsx"
            
            if not filename.endswith('.xlsx'):
                filename += '.xlsx'
            
            filepath = self.output_dir / filename
            
            # Create workbook
            wb = Workbook()
            
            # Remove default sheet if we have multiple sheets
            if isinstance(data, dict) and len(data) > 1:
                wb.remove(wb.active)
            
            # Process data
            if isinstance(data, dict):
                # Multiple sheets
                for sheet_name, sheet_data in data.items():
                    ws = wb.create_sheet(title=sheet_name)
                    self._add_data_to_excel_sheet(ws, sheet_data, headers)
            else:
                # Single sheet
                ws = wb.active
                ws.title = sheet_name
                self._add_data_to_excel_sheet(ws, data, headers)
            
            # Save workbook
            wb.save(str(filepath))
            
            logger.info(f"Excel spreadsheet generated: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error generating Excel spreadsheet: {e}", exc_info=True)
            return None
    
    def generate_from_template(self,
                               template_data: Dict,
                               doc_type: str = "pdf",
                               filename: str = None,
                               variables: Dict[str, Any] = None) -> Optional[str]:
        """
        Generate document from template data
        
        Args:
            template_data: Template structure (from database)
            doc_type: 'pdf', 'docx', or 'xlsx'
            filename: Output filename
            variables: Variables to fill in template placeholders
        
        Returns:
            Path to generated document or None if failed
        """
        try:
            # Fill template variables
            content = self._fill_template(template_data, variables or {})
            
            # Generate based on type
            if doc_type.lower() == 'pdf':
                return self.generate_pdf(content, filename=filename, **template_data.get('options', {}))
            elif doc_type.lower() == 'docx':
                return self.generate_word(content, filename=filename, **template_data.get('options', {}))
            elif doc_type.lower() == 'xlsx':
                return self.generate_excel(content, filename=filename, **template_data.get('options', {}))
            else:
                logger.error(f"Unknown document type: {doc_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating from template: {e}", exc_info=True)
            return None
    
    def _process_structured_content(self, content: Dict, styles) -> List:
        """Process structured content dict for PDF"""
        story = []
        
        for section in content.get('sections', []):
            # Section title
            if 'title' in section:
                story.append(Paragraph(section['title'], styles['Heading2']))
                story.append(Spacer(1, 0.1*inch))
            
            # Section content
            if 'content' in section:
                if isinstance(section['content'], list):
                    for item in section['content']:
                        story.append(Paragraph(str(item), styles['Normal']))
                        story.append(Spacer(1, 0.05*inch))
                else:
                    story.append(Paragraph(str(section['content']), styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
            
            # Tables
            if 'table' in section:
                table_data = section['table']
                if isinstance(table_data, list) and len(table_data) > 0:
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 14),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 0.2*inch))
        
        return story
    
    def _add_structured_content_to_word(self, doc: Document, content: Dict):
        """Add structured content to Word document"""
        for section in content.get('sections', []):
            if 'title' in section:
                doc.add_heading(section['title'], level=2)
            
            if 'content' in section:
                if isinstance(section['content'], list):
                    for item in section['content']:
                        doc.add_paragraph(str(item))
                else:
                    doc.add_paragraph(str(section['content']))
            
            if 'table' in section:
                table_data = section['table']
                if isinstance(table_data, list) and len(table_data) > 0:
                    table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
                    for i, row_data in enumerate(table_data):
                        for j, cell_data in enumerate(row_data):
                            table.rows[i].cells[j].text = str(cell_data)
    
    def _markdown_to_word(self, doc: Document, markdown_text: str):
        """Convert markdown to Word document"""
        html = markdown.markdown(markdown_text, extensions=['extra', 'codehilite'])
        
        # Simple conversion - split by paragraphs
        paragraphs = markdown_text.split('\n\n')
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Check for headers
            if para.startswith('#'):
                level = len(para) - len(para.lstrip('#'))
                text = para.lstrip('#').strip()
                doc.add_heading(text, level=min(level, 9))
            elif para.startswith('-') or para.startswith('*'):
                # List item
                doc.add_paragraph(para.lstrip('-*').strip(), style='List Bullet')
            else:
                doc.add_paragraph(para)
    
    def _add_data_to_excel_sheet(self, ws, data: List[List[Any]], headers: List[str] = None):
        """Add data to Excel worksheet with formatting"""
        # Add headers if provided
        if headers:
            header_row = 1
            for col_idx, header in enumerate(headers, 1):
                cell = ws.cell(row=header_row, column=col_idx, value=header)
                cell.font = Font(bold=True, size=12)
                cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
                cell.font = Font(bold=True, color="FFFFFF", size=12)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            
            # Start data from row 2
            start_row = 2
        else:
            start_row = 1
        
        # Add data
        for row_idx, row_data in enumerate(data, start=start_row):
            for col_idx, cell_value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=cell_value)
                cell.alignment = Alignment(horizontal="left", vertical="center")
        
        # Auto-adjust column widths
        for col_idx in range(1, max(len(row) for row in data) + 1):
            column_letter = get_column_letter(col_idx)
            max_length = 0
            for row in data:
                if col_idx <= len(row):
                    try:
                        if len(str(row[col_idx - 1])) > max_length:
                            max_length = len(str(row[col_idx - 1]))
                    except:
                        pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
    
    def _html_to_paragraphs(self, html: str, styles) -> List:
        """Convert HTML to ReportLab paragraphs (simplified)"""
        story = []
        # Simple HTML parsing - split by tags
        # Remove HTML tags for now (can be enhanced)
        text = re.sub(r'<[^>]+>', '', html)
        paragraphs = text.split('\n')
        for para in paragraphs:
            if para.strip():
                story.append(Paragraph(para.strip(), styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
        return story
    
    def _is_markdown(self, text: str) -> bool:
        """Check if text appears to be markdown"""
        markdown_patterns = [
            r'^#{1,6}\s',  # Headers
            r'^\*\s',      # Bullet lists
            r'^\d+\.\s',   # Numbered lists
            r'\*\*.*\*\*', # Bold
            r'`.*`',       # Code
            r'\[.*\]\(.*\)', # Links
        ]
        return any(re.search(pattern, text, re.MULTILINE) for pattern in markdown_patterns)
    
    def _fill_template(self, template_data: Dict, variables: Dict[str, Any]) -> Union[str, Dict]:
        """Fill template placeholders with variables"""
        import json
        
        # Convert template_data to string for replacement
        template_str = json.dumps(template_data) if isinstance(template_data, dict) else str(template_data)
        
        # Replace placeholders {variable_name}
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            template_str = template_str.replace(placeholder, str(value))
        
        # Also replace common placeholders
        common_vars = {
            '{date}': datetime.now().strftime('%Y-%m-%d'),
            '{time}': datetime.now().strftime('%H:%M:%S'),
            '{datetime}': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        for placeholder, value in common_vars.items():
            template_str = template_str.replace(placeholder, value)
        
        # Try to parse back to dict if it was a dict
        try:
            return json.loads(template_str)
        except:
            return template_str


# Global instance
_document_generator_instance = None

def get_document_generator(output_dir: str = "generated_documents") -> DocumentGenerator:
    """Get or create global document generator instance"""
    global _document_generator_instance
    if _document_generator_instance is None:
        _document_generator_instance = DocumentGenerator(output_dir)
    return _document_generator_instance
