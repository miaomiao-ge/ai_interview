# AI 面试系统面试结果回传接口

本文档用于对方系统从 AI 面试系统获取国际学生面试结果数据。接口流程与“获取国际学生基础信息、个人照片接口”保持一致：

1. 先通过 GET 接口获取 token。
2. 再通过 POST `x-www-form-urlencoded` 批量获取指定年份的申请与面试结果数据。

## 1. GET 获取 token

### 请求地址

```http
GET {BASE_URL}/api/external/interviewResult/getToken
```

### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| appKey | query | string | 是 | 客户端标识，由 AI 面试系统提供 |
| appSecret | query | string | 是 | 客户端密钥，由 AI 面试系统提供 |

### 请求示例

```bash
curl -G "{BASE_URL}/api/external/interviewResult/getToken" \
  --data-urlencode "appKey=your-app-key" \
  --data-urlencode "appSecret=your-app-secret"
```

### 成功返回示例

```json
{
  "result": "1",
  "message": "token生成成功!",
  "dataObject": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "valid": true
}
```

### 失败返回示例

```json
{
  "result": "0",
  "message": "appKey不正确",
  "dataObject": null,
  "valid": false
}
```

## 2. POST 批量获取申请面试结果

### 请求地址

```http
POST {BASE_URL}/api/external/interviewResult/getApplicationInfoBatch
```

### Content-Type

```http
application/x-www-form-urlencoded
```

### 请求参数

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| token | body | string | 是 | 第 1 步获取到的 token |
| year | body | string | 是 | 申请年份，例如 `2026` |
| pageNum | body | integer | 是 | 页码，从 `1` 开始 |
| pageSize | body | integer | 是 | 每页数量，范围 `1-100` |
| applicationNos | body | string | 否 | 申请编号，多个用英文逗号分隔 |
| ids | body | string | 否 | 申请唯一标识 `id`，多个用英文逗号分隔 |
| includeIncomplete | body | string | 否 | 是否包含未完成/未成功评价的记录，默认 `false` |

### 请求示例

```bash
curl -X POST "{BASE_URL}/api/external/interviewResult/getApplicationInfoBatch" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d "year=2026" \
  -d "pageNum=1" \
  -d "pageSize=100"
```

按申请编号过滤：

```bash
curl -X POST "{BASE_URL}/api/external/interviewResult/getApplicationInfoBatch" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=TOKEN_VALUE" \
  -d "year=2026" \
  -d "pageNum=1" \
  -d "pageSize=100" \
  -d "applicationNos=20260600003,20260600004"
```

按申请唯一标识过滤：

```bash
curl -X POST "{BASE_URL}/api/external/interviewResult/getApplicationInfoBatch" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=TOKEN_VALUE" \
  -d "year=2026" \
  -d "pageNum=1" \
  -d "pageSize=100" \
  -d "ids=APP-UNIQUE-1,APP-UNIQUE-2"
```

### 成功返回示例

```json
{
  "result": "1",
  "message": "请求成功!",
  "dataObject": {
    "pageNum": 1,
    "pageSize": 100,
    "totalCount": 1,
    "year": "2026",
    "data": [
      {
        "name": "DU TEST",
        "familyName": "TEST",
        "givenName": "DU",
        "id": "APP-UNIQUE-1",
        "applicationNo": "20260600003",
        "flag": "1",
        "passportNumber": "AQ1234567",
        "email": "student@example.com",
        "interviewResult": {
          "recordId": 12,
          "sessionId": "session-1",
          "status": "success",
          "archiveStatus": "success",
          "archiveError": "",
          "reviewStatus": "待复核",
          "reviewRemark": "",
          "report": "综合得分：88/100\n...",
          "structured": {
            "total_score": 88,
            "dimension_scores": [
              {
                "name": "语言能力",
                "score": 18,
                "comment": "表达清楚"
              }
            ],
            "summary": "整体表现良好",
            "strengths": ["表达清楚"],
            "improvements": ["补充研究计划"]
          },
          "totalScore": 88,
          "dimensionScores": [
            {
              "name": "语言能力",
              "score": 18,
              "comment": "表达清楚"
            }
          ],
          "summary": "整体表现良好",
          "strengths": ["表达清楚"],
          "improvements": ["补充研究计划"],
          "chatHistory": "完整面试问答记录",
          "faceVerification": {
            "status": "passed",
            "score": 91.2,
            "verifiedAt": "2026-07-09T10:00:00",
            "snapshotOssKey": "face/snapshot.jpg",
            "identityDocOssKey": "face/doc.jpg"
          },
          "proctoring": {
            "riskLevel": "low",
            "flags": {}
          },
          "media": {
            "audioPath": "",
            "videoPath": "",
            "avPath": "https://oss.example/interview.mp4"
          },
          "timestamps": {
            "submittedAt": "2026-07-09T10:01:00",
            "completedAt": "2026-07-09T10:20:00",
            "processingStartedAt": "2026-07-09T10:19:00",
            "processingFinishedAt": "2026-07-09T10:20:00",
            "createdAt": "2026-07-09T10:00:00"
          }
        }
      }
    ]
  },
  "valid": true
}
```

### 失败返回示例

```json
{
  "result": "0",
  "message": "token已过期，请重新获取",
  "dataObject": null,
  "valid": false
}
```

## 3. 字段说明

### 学生申请字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| name | string | 学生姓名 |
| familyName | string | 学生护照姓 |
| givenName | string | 学生护照名 |
| id | string | 申请唯一标识 |
| applicationNo | string | 申请编号 |
| flag | string | 是否为中介推荐的学生，值按来源系统原样返回 |
| passportNumber | string | 护照号 |
| email | string | 邮箱 |

### 面试结果字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| interviewResult.report | string | AI 面试系统生成的文字面试报告 |
| interviewResult.totalScore | number | 总分 |
| interviewResult.dimensionScores | array | 各维度得分和评价 |
| interviewResult.summary | string | 总结 |
| interviewResult.strengths | array | 优势 |
| interviewResult.improvements | array | 改进建议 |
| interviewResult.chatHistory | string | 完整面试问答记录 |
| interviewResult.faceVerification | object | 人脸核验状态、分数、时间与证明材料 OSS key |
| interviewResult.proctoring | object | 监考风险等级与异常标记 |
| interviewResult.media | object | 面试音视频归档路径 |
| interviewResult.timestamps | object | 面试提交、完成、处理时间 |

## 4. 服务端配置

AI 面试系统服务器需要配置：

```env
EXTERNAL_RESULT_APP_KEY=your-app-key
EXTERNAL_RESULT_APP_SECRET=your-app-secret
EXTERNAL_RESULT_TOKEN_EXPIRE_SECONDS=86400
```

`EXTERNAL_RESULT_TOKEN_EXPIRE_SECONDS` 默认 86400 秒，也就是 24 小时。
