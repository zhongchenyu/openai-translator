import shutil
from typing import Optional
from model import Model
from translator.pdf_parser import PDFParser
from translator.writer import Writer
import pymupdf  # PyMuPDF
from utils import LOG
import json
from book.content import Content, ContentType


class PDFTranslator:
    def __init__(self, model: Model):
        self.model = model
        self.pdf_parser = PDFParser()
        self.writer = Writer()

    def translate_pdf(self, pdf_file_path: str, file_format: str = 'PDF', target_language: str = '中文', output_file_path: str = None, pages: Optional[int] = None):
        self.book = self.pdf_parser.parse_pdf(pdf_file_path, pages)

        for page_idx, page in enumerate(self.book.pages):
            for content_idx, content in enumerate(page.contents):
                prompt = self.model.translate_prompt(content, target_language)
                LOG.debug(prompt)
                translation, status = self.model.make_request(prompt)
                if not status:
                    LOG.error('make request fail!')
                    raise Exception('make request fail!')
                else:
                    LOG.info(translation)
                
                # Update the content in self.book.pages directly
                self.book.pages[page_idx].contents[content_idx].set_translation(translation, status)

        self.writer.save_translated_book(self.book, output_file_path, file_format)

    def translate_pdf_formated(self,pdf_file_path: str, file_format: str = 'PDF', target_language: str = '中文', output_file_path: str = None, pages: Optional[int] = None):
        if file_format.lower()=='pdf':
            pdf_text = self.collect_pdf_text(pdf_file_path)
            content = Content(ContentType.TEXT,json.dumps(list(pdf_text)))
            prompt = self.model.translate_prompt(content, target_language)
            LOG.debug(prompt)
            translation, status = self.model.make_request(prompt)
            if not status:
                LOG.error('make request fail!')
                raise Exception('make request fail!')
            else:
                LOG.info(translation)
            translation_dict = dict(zip(pdf_text,json.loads(translation)))

            # shutil.copy(pdf_file_path, output_file_path)
            self.replace_pdf_text(pdf_file_path,output_file_path,translation_dict)

        else:
            self.translate_pdf(pdf_file_path, file_format, target_language, output_file_path, pages)


    def collect_pdf_text(self, input_pdf_path):
        """
        替换 PDF 中的文本，保留原格式和布局
        :param input_pdf_path: 输入 PDF 路径
        :param output_pdf_path: 输出 PDF 路径
        :param translation_dict: 翻译字典，格式为 {原文本: 翻译后文本}
        """
        doc = pymupdf.open(input_pdf_path)
        pdf_text = set()
        for page in doc:
            # 获取所有文本块及其属性
            blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]

            for block in blocks:
                if block["type"] == 0:  # 仅处理文本块
                    for line in block["lines"]:
                        for span in line["spans"]:
                            original_text = span["text"]
                            pdf_text.add(original_text)
        doc.close()
        LOG.debug(f"pdf_text: {pdf_text}")
        return pdf_text

    def replace_pdf_text(self,input_pdf_path,output_pdf_path,translation_dict):
        """
        替换 PDF 中的文本，保留原格式和布局
        :param input_pdf_path: 输入 PDF 路径
        :param output_pdf_path: 输出 PDF 路径
        :param translation_dict: 翻译字典，格式为 {原文本: 翻译后文本}
        """
        LOG.debug(f"translation_dict: \n")
        for k,v in translation_dict.items():
            LOG.debug(f"{k} --- {v}")
        doc = pymupdf.open(input_pdf_path)

        for page in doc:
            # 获取所有文本块及其属性
            blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]

            for block in blocks:
                if block["type"] == 0:  # 仅处理文本块
                    for line in block["lines"]:
                        for span in line["spans"]:
                            original_text = span["text"]
                            font = self.get_safe_font(span["font"])
                            color = self.decode_color(span["color"])  # 转换颜色值

                            new_text = translation_dict.get(original_text,original_text)
                            print(original_text,' ||| ',new_text)

                            # 删除原文本
                            rect = pymupdf.Rect(span["bbox"])
                            page.add_redact_annot(rect)
                            page.apply_redactions()

                            # 插入翻译后的文本（保持原位置和样式）
                            page.insert_text(
                                # rect.tl,  # 左上角坐标
                                (rect.tl.x, rect.tl.y + span["size"]*0.6),  # 调整 Y 坐标
                                new_text,
                                fontname=font["fontname"],
                                fontfile=font["fontfile"],
                                fontsize=span["size"],
                                color=color,
                            )

        # 保存修改后的 PDF（保留图片、表格等非文本内容）
        doc.save(output_pdf_path, ) # incremental=True, garbage=4, deflate=True
        doc.close()

    def get_safe_font(self,fontname):
        base14_fonts = [
            "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
            "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
            "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
            "Symbol", "ZapfDingbats"
        ]
        if fontname in base14_fonts:
            return {'fontname': fontname, "fontfile": None}
        else:
            return {'fontname': "SimSum", 'fontfile': "fonts/simsun.ttc"}

    def decode_color(self,color_int):
        """
        将整数颜色值转换为 [r, g, b] 格式，每个分量在 [0, 1] 范围内。
        """
        r = (color_int >> 16) & 0xFF  # 提取红色分量
        g = (color_int >> 8) & 0xFF  # 提取绿色分量
        b = color_int & 0xFF  # 提取蓝色分量
        return [r / 255, g / 255, b / 255]  # 归一化到 [0, 1]