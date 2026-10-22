from __future__ import annotations


def friendly_llm_error(exc: BaseException) -> str:
    """把 OpenAI SDK / 百炼等 API 异常转成页面可读说明。"""
    text = str(exc)
    if "Arrearage" in text or "overdue-payment" in text:
        return (
            "阿里云百炼返回 Arrearage：账户欠费或未开通按量计费，API 被拒绝。"
            "请到百炼控制台充值/开通计费后重试；或暂时在 .env 注释 LLM_*，改用本地 Ollama。"
            "说明：https://help.aliyun.com/zh/model-studio/error-code#overdue-payment"
        )
    if "invalid_api_key" in text or "Incorrect API key" in text:
        return (
            "API Key 无效或与 Base URL 地域不匹配。"
            "请核对 LLM_API_KEY、LLM_BASE_URL（北京 Key 配 dashscope.aliyuncs.com）。"
        )
    if len(text) > 600:
        return text[:600] + "…"
    return text
