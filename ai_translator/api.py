import os
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from model.openai_model import OpenAIModel
from translator.pdf_translator import PDFTranslator
from datetime import datetime
from utils.config_loader import ConfigLoader
from utils.logger import LOG
app = Flask(__name__)
CORS(app)  # 允许所有来源的跨域请求

# 配置上传和输出目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 获取脚本所在目录
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'files/uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'files/outputs')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/upload', methods=['POST'])
def upload_file():
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    config_loader = ConfigLoader('config.yaml')
    config = config_loader.load_config()


    model_name = request.form.get('model_name', config['OpenAIModel']['model'])
    api_key = request.form.get('openai_api_key', config['OpenAIModel']['api_key'] or os.getenv('OPENAI_API_KEY'))
    file_format = request.form.get('file_format',None)
    target_language = request.form.get('target_language', None)
    if not (model_name and api_key and file_format and target_language):
        return jsonify({'error': 'missing params'}), 400

    # 检查是否有文件上传
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']

    # 检查文件名是否为空
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # 检查文件扩展名是否允许
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # 保存上传的文件
    filename =file.filename
    input_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(input_file_path)

    # 构造输出文件路径
    output_filename = f"{os.path.splitext(filename)[0]}_{current_time}.{'md' if file_format.lower()=='markdown' else file_format}"
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)


    print("processing translation...")

    # 实例化 PDFTranslator 类，并调用 translate_pdf() 方法
    model = OpenAIModel(model=model_name, api_key=api_key)
    translator = PDFTranslator(model)
    try:
        translator.translate_pdf_formated(input_file_path, file_format,target_language=target_language,output_file_path=output_path)
    except Exception as e:
        LOG.error(e)
        return jsonify({"error":"Translate fail"}), 500

    # 返回下载链接
    download_url = f"/download/{output_filename}"
    # 清理临时文件
    if os.path.exists(input_file_path):
        os.remove(input_file_path)
    return jsonify({"message": "File converted successfully", "download_url": download_url}), 200






@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """提供文件下载"""
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if not os.path.exists(output_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(output_path, as_attachment=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0',port=8081,debug=True)