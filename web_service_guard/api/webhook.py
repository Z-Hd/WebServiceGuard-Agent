from flask import Flask, request, jsonify
from web_service_guard.workflow.repair_pipeline import RepairPipeline

app = Flask(__name__)
pipeline = RepairPipeline()

@app.route('/webhook', methods=['POST'])
def webhook():
    """接收webhook请求"""
    try:
        data = request.json
        service = data.get('service')
        repo = data.get('repo')
        branch = data.get('branch')
        
        if not service or not repo or not branch:
            return jsonify({
                "status": "FAILED",
                "message": "缺少必要参数"
            }), 400
        
        # 运行修复流水线
        result = pipeline.run(service, repo, branch)
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({
            "status": "FAILED",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)