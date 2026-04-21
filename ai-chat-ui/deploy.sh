#!/bin/bash
echo "构建前端..."
npm run build

echo "上传到服务器..."
scp -r dist/* myserver:/home/admin/ai-system/dist/

echo "部署完成！"
