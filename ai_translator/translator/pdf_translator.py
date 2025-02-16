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
            pdf_text = list(set(pdf_text))
            content = Content(ContentType.TEXT,json.dumps(pdf_text))
            prompt = self.model.translate_prompt(content, target_language)
            LOG.debug(prompt)
            attempt = 0
            max_time = 5
            while attempt<=max_time:
                attempt += 1
                translation, status = self.model.make_request(prompt)
                if not status:
                    LOG.error('make request fail!')
                    raise Exception('make request fail!')
                else:
                    LOG.info(translation)
                translation_list = json.loads(translation)
                if translation_list != pdf_text and len(pdf_text)==len(translation_list):
                    break
                else:

                    LOG.info(f'request {attempt} time(s), {"not translate" if translation_list == pdf_text else "miss content"}')
                    LOG.debug(f"translation_list==pdf_text:{translation_list==pdf_text},len(pdf_text):{len(pdf_text)},len(translation_list):{len(translation_list)}")
                    if attempt>=max_time:
                        raise Exception('receive wrong translation content!')
                    LOG.info("retry...")
            translation_dict = dict(zip(pdf_text,translation_list))

            # shutil.copy(pdf_file_path, output_file_path)
            self.replace_pdf_text(pdf_file_path,output_file_path,translation_dict,target_language)

        else:
            self.translate_pdf(pdf_file_path, file_format, target_language, output_file_path, pages)


    def collect_pdf_text(self, input_pdf_path):
        doc = pymupdf.open(input_pdf_path)
        pdf_text = []
        for page in doc:
            blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]

            for block in blocks:
                if block["type"] == 0:  # 仅处理文本块
                    for line in block["lines"]:
                        for span in line["spans"]:
                            original_text = span["text"]
                            pdf_text.append(original_text)
        doc.close()
        LOG.debug(f"pdf_text: {pdf_text}")
        return pdf_text

    def replace_pdf_text(self,input_pdf_path,output_pdf_path,translation_dict,target_language):
        LOG.debug(f"translation_dict: \n")
        # for k,v in translation_dict.items():
        #     LOG.debug(f"{k} --- {v}")
        doc = pymupdf.open(input_pdf_path)

        for page in doc:
            blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]

            for block in blocks:
                if block["type"] == 0:  # 仅处理文本块
                    for line in block["lines"]:
                        for span in line["spans"]:
                            original_text = span["text"]
                            font = self.get_safe_font(span["font"],target_language)
                            # LOG.debug(f"font: {font}")
                            color = self.decode_color(span["color"])  # 转换颜色值

                            new_text = translation_dict.get(original_text,original_text)
                            LOG.debug(f"{original_text} ||| {new_text}")

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
        doc.save(output_pdf_path, )
        doc.close()

    def get_safe_font(self,fontname,target_language):
        base14_fonts = [
            "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
            "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
            "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
            "Symbol", "ZapfDingbats"
        ]
        if target_language in {'中文','日语'}:
            return {'fontname': "SimSum", 'fontfile': "fonts/simsun.ttc"}
        elif fontname in base14_fonts:
            return {'fontname': fontname, "fontfile": None}
        else:
            return {'fontname': "helv", 'fontfile': None}

    def decode_color(self,color_int):
        """
        将整数颜色值转换为 [r, g, b] 格式，每个分量在 [0, 1] 范围内。
        """
        r = (color_int >> 16) & 0xFF  # 提取红色分量
        g = (color_int >> 8) & 0xFF  # 提取绿色分量
        b = color_int & 0xFF  # 提取蓝色分量
        return [r / 255, g / 255, b / 255]  # 归一化到 [0, 1]