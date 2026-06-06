"""
AI Commerce Pro - 欧洲跨境电商 TikTok 自动化流水线
支持市场: UK / DE / FR / IT / ES
参考: github.com/makiisthenes/TiktokAutoUploader
"""

import os
import re
import uuid
import logging
import subprocess
from contextlib import asynccontextmanager
from typing import Optional
from enum import Enum

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =========================
# 初始化
# =========================
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ai-commerce")

task_store: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 AI Commerce Pro 启动（欧洲市场版）")
    yield
    logger.info("🛑 服务关闭")

app = FastAPI(title="AI Commerce Pro - EU", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# =========================
# 枚举 & 常量
# =========================
class Market(str, Enum):
    UK = "UK"
    DE = "DE"
    FR = "FR"
    IT = "IT"
    ES = "ES"

class VideoStyle(str, Enum):
    UNBOXING    = "unboxing"       # 开箱风格
    PROBLEM_SOLVE = "problem_solve"  # 痛点解决
    BEFORE_AFTER = "before_after"  # 前后对比
    LIFESTYLE   = "lifestyle"      # 生活方式植入
    TUTORIAL    = "tutorial"       # 教程演示
    UGCREVIEW   = "ugc_review"     # 真实用户评测

# 各市场语言映射
MARKET_LANG = {
    Market.UK: "English",
    Market.DE: "German",
    Market.FR: "French",
    Market.IT: "Italian",
    Market.ES: "Spanish",
}

# 各市场货币
MARKET_CURRENCY = {
    Market.UK: "£",
    Market.DE: "€",
    Market.FR: "€",
    Market.IT: "€",
    Market.ES: "€",
}


# =========================
# 欧洲爆款商品库（基于 FastMoss/Kalodata 2025-2026 数据）
# =========================
EUROPE_PRODUCT_CATALOG = [

    # ── 美妆 & 护肤（全欧洲 #1 品类）──
    {"title": "Teeth Whitening Kit",        "price": 29.99, "cost": 6.0,  "trend": 0.97, "category": "Beauty", "markets": ["UK","DE","FR","IT","ES"], "style": "before_after"},
    {"title": "Vitamin C Serum 30ml",        "price": 24.99, "cost": 5.5,  "trend": 0.95, "category": "Skincare", "markets": ["UK","FR","DE"], "style": "ugc_review"},
    {"title": "Gua Sha Facial Tool",         "price": 19.99, "cost": 4.0,  "trend": 0.92, "category": "Beauty", "markets": ["UK","FR","DE","IT"], "style": "tutorial"},
    {"title": "LED Face Mask",               "price": 49.99, "cost": 12.0, "trend": 0.91, "category": "Beauty", "markets": ["UK","DE","FR"], "style": "before_after"},
    {"title": "Perfume Roller Ball Set",     "price": 34.99, "cost": 8.0,  "trend": 0.88, "category": "Beauty", "markets": ["FR","IT","ES"], "style": "lifestyle"},
    {"title": "Collagen Eye Patches",        "price": 15.99, "cost": 3.5,  "trend": 0.93, "category": "Skincare", "markets": ["UK","DE","FR","IT","ES"], "style": "ugc_review"},

    # ── 健康 & 健身 ──
    {"title": "Massage Gun Mini",            "price": 39.99, "cost": 10.0, "trend": 0.90, "category": "Health", "markets": ["UK","DE","FR"], "style": "problem_solve"},
    {"title": "Resistance Bands Set",        "price": 22.99, "cost": 5.0,  "trend": 0.89, "category": "Fitness", "markets": ["UK","DE","ES"], "style": "tutorial"},
    {"title": "Smart Jump Rope",             "price": 29.99, "cost": 7.0,  "trend": 0.86, "category": "Fitness", "markets": ["UK","DE","FR","ES"], "style": "tutorial"},
    {"title": "Posture Corrector",           "price": 27.99, "cost": 6.5,  "trend": 0.88, "category": "Health", "markets": ["UK","DE","FR","IT"], "style": "problem_solve"},
    {"title": "Protein Shaker Bottle",       "price": 18.99, "cost": 4.5,  "trend": 0.84, "category": "Fitness", "markets": ["UK","DE","ES"], "style": "lifestyle"},

    # ── 智能家居（德国强势品类）──
    {"title": "Smart Plug Wi-Fi 4-Pack",     "price": 32.99, "cost": 8.0,  "trend": 0.94, "category": "Smart Home", "markets": ["DE","UK","FR"], "style": "tutorial"},
    {"title": "LED Strip Lights 5m",         "price": 24.99, "cost": 5.5,  "trend": 0.92, "category": "Smart Home", "markets": ["DE","UK","FR","IT"], "style": "lifestyle"},
    {"title": "Mini Projector 1080p",        "price": 79.99, "cost": 22.0, "trend": 0.87, "category": "Electronics", "markets": ["DE","UK","FR"], "style": "unboxing"},
    {"title": "Robot Vacuum Mini",           "price": 89.99, "cost": 25.0, "trend": 0.89, "category": "Smart Home", "markets": ["DE","UK"], "style": "before_after"},
    {"title": "Air Purifier Desktop",        "price": 54.99, "cost": 15.0, "trend": 0.85, "category": "Smart Home", "markets": ["DE","FR","IT"], "style": "problem_solve"},

    # ── 时尚配饰（法国/意大利强势）──
    {"title": "Minimalist Gold Necklace",    "price": 29.99, "cost": 5.0,  "trend": 0.93, "category": "Fashion", "markets": ["FR","IT","ES","UK"], "style": "lifestyle"},
    {"title": "Stainless Steel Watch",       "price": 44.99, "cost": 10.0, "trend": 0.87, "category": "Fashion", "markets": ["FR","DE","IT"], "style": "lifestyle"},
    {"title": "Canvas Tote Bag",             "price": 19.99, "cost": 4.0,  "trend": 0.86, "category": "Fashion", "markets": ["FR","IT","ES"], "style": "lifestyle"},
    {"title": "Silk Scrunchie Set",          "price": 14.99, "cost": 3.0,  "trend": 0.90, "category": "Fashion", "markets": ["FR","IT","ES","UK"], "style": "ugc_review"},

    # ── 厨房 & 生活（全欧洲热销）──
    {"title": "Portable Blender USB",        "price": 34.99, "cost": 9.0,  "trend": 0.91, "category": "Kitchen", "markets": ["UK","DE","FR","IT","ES"], "style": "tutorial"},
    {"title": "Beeswax Food Wraps 3-Pack",   "price": 19.99, "cost": 4.5,  "trend": 0.88, "category": "Kitchen", "markets": ["UK","DE","FR"], "style": "problem_solve"},
    {"title": "Insulated Stanley-Style Cup", "price": 27.99, "cost": 7.0,  "trend": 0.95, "category": "Kitchen", "markets": ["UK","DE","FR","ES"], "style": "lifestyle"},
    {"title": "Magnetic Knife Strip",        "price": 22.99, "cost": 5.5,  "trend": 0.82, "category": "Kitchen", "markets": ["DE","FR","IT"], "style": "tutorial"},

    # ── 宠物用品（英国 #1 市场）──
    {"title": "Interactive Cat Toy",         "price": 24.99, "cost": 5.5,  "trend": 0.94, "category": "Pets", "markets": ["UK","DE","FR"], "style": "ugc_review"},
    {"title": "Dog GPS Tracker",             "price": 39.99, "cost": 10.0, "trend": 0.89, "category": "Pets", "markets": ["UK","DE"], "style": "problem_solve"},

    # ── 儿童 & 教育（西班牙/意大利）──
    {"title": "Montessori Wooden Puzzle",    "price": 29.99, "cost": 7.0,  "trend": 0.87, "category": "Kids", "markets": ["ES","IT","FR"], "style": "tutorial"},
    {"title": "Night Light Projector Kids",  "price": 32.99, "cost": 8.0,  "trend": 0.88, "category": "Kids", "markets": ["ES","IT","FR","UK"], "style": "lifestyle"},
]


# =========================
# 数据模型
# =========================
class Product(BaseModel):
    title: str
    price: float
    cost: float
    trend: float
    category: str
    markets: list[str]
    style: str


class PipelineConfig(BaseModel):
    target_market: Market = Market.UK
    min_profit_margin: float = 0.60
    min_trend_score: float = 0.85
    max_products: int = 3
    video_style_override: Optional[VideoStyle] = None


class PipelineResult(BaseModel):
    product: str
    market: str
    video_path: str
    script_preview: str
    profit_margin: float
    video_style: str
    category: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    results: Optional[list] = None
    error: Optional[str] = None


# =========================
# 1. 选品系统（欧洲版）
# =========================
def get_products() -> list[Product]:
    return [Product(**p) for p in EUROPE_PRODUCT_CATALOG]


def filter_products(
    products: list[Product],
    config: PipelineConfig
) -> list[Product]:
    """按利润率、趋势、目标市场筛选"""
    result = []
    for p in products:
        margin = (p.price - p.cost) / p.price
        in_market = config.target_market.value in p.markets

        if margin >= config.min_profit_margin and p.trend >= config.min_trend_score and in_market:
            logger.info(f"✅ [{config.target_market}] {p.title} | 利润率:{margin:.0%} 趋势:{p.trend}")
            result.append(p)

    # 按趋势分排序，取前N个
    result.sort(key=lambda x: x.trend, reverse=True)
    return result[:config.max_products]


# =========================
# 2. AI 脚本生成（多语言 + 多风格）
# =========================
VIDEO_STYLE_PROMPTS = {
    VideoStyle.UNBOXING: "开箱视频风格：从包装到产品展示，制造惊喜感，强调「刚收到」的真实感",
    VideoStyle.PROBLEM_SOLVE: "痛点解决风格：先展示问题（30%）→ 介绍产品（40%）→ 效果对比（30%），强烈情绪共鸣",
    VideoStyle.BEFORE_AFTER: "前后对比风格：震撼的变化效果，使用前后强烈反差，制造wow moment",
    VideoStyle.LIFESTYLE: "生活方式植入：自然场景中使用产品，营造向往的生活感，不像广告的广告",
    VideoStyle.TUTORIAL: "教程演示风格：step-by-step展示，清晰简洁，突出操作简单，人人都能用",
    VideoStyle.UGCREVIEW: "真实用户评测：真实口吻，先说疑虑→使用体验→真实结论，增强可信度",
}

def generate_script(product: Product, config: PipelineConfig) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置")

    market = config.target_market
    lang = MARKET_LANG[market]
    currency = MARKET_CURRENCY[market]
    style_key = VideoStyle(config.video_style_override or product.style)
    style_desc = VIDEO_STYLE_PROMPTS[style_key]

    prompt = f"""你是TikTok欧洲市场爆款营销专家，专注 {market.value} 市场。

【商品信息】
- 商品: {product.title}
- 类目: {product.category}
- 售价: {currency}{product.price}
- 目标市场: {market.value}（{lang}）

【视频风格要求】
{style_desc}

【生成要求】
请用 {lang} 语言生成完整TikTok视频脚本：

1. **Hook（前3秒）**: 一句话抓住注意力，制造好奇或共鸣
2. **视频脚本（15秒）**: 分镜描述 + 旁白文案
3. **CTA（行动号召）**: 结尾引导购买或评论
4. **字幕文案**: 屏幕上显示的关键文字（简短有力）
5. **Hashtags**: 8个精准标签（英文+{lang}混合）

风格要求：真实、不油腻、符合{market.value}用户审美，避免过于中国风的营销话术。"""

    try:
        res = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.85,
                "max_tokens": 800,
            },
            timeout=30
        )
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        logger.info(f"🤖 脚本生成成功: {product.title} [{market}]")
        return content

    except requests.Timeout:
        raise RuntimeError(f"DeepSeek API 超时: {product.title}")
    except requests.HTTPError as e:
        raise RuntimeError(f"DeepSeek API 错误 {e.response.status_code}: {e.response.text[:200]}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"响应解析失败: {e}")


# =========================
# 3. 视频生成（ffmpeg 欧洲风格）
# =========================

# 视频风格 → 背景色配置
STYLE_COLORS = {
    VideoStyle.UNBOXING:      "0x1C1C2E",   # 深夜蓝
    VideoStyle.PROBLEM_SOLVE: "0x0D1117",   # 极深黑
    VideoStyle.BEFORE_AFTER:  "0x1A0A2E",   # 深紫
    VideoStyle.LIFESTYLE:     "0xFFF8F0",   # 奶白暖调
    VideoStyle.TUTORIAL:      "0x0F2027",   # 深青
    VideoStyle.UGCREVIEW:     "0x1E1E1E",   # 中性深灰
}

FONT_COLOR_MAP = {
    VideoStyle.LIFESTYLE: "black",
}

def safe_filename(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text)


def extract_caption(script: str) -> str:
    """从脚本中提取字幕文案（关键文字段落）"""
    lines = script.split("\n")
    captions = []
    capture = False
    for line in lines:
        if "字幕" in line or "Caption" in line or "屏幕" in line:
            capture = True
            continue
        if capture and line.strip():
            captions.append(line.strip().lstrip("-•*").strip())
            if len(captions) >= 3:
                break
        if capture and not line.strip() and captions:
            break

    if captions:
        return " | ".join(captions)[:120]
    # fallback: 取脚本前80字
    return script.replace("\n", " ")[:80]


def create_video(script: str, product: Product, market: str) -> str:
    """生成 TikTok 竖屏视频 1080x1920"""
    style_key = VideoStyle(product.style)
    bg_color = STYLE_COLORS.get(style_key, "0x1a1a2e")
    font_color = FONT_COLOR_MAP.get(style_key, "white")

    safe_name = safe_filename(f"{product.title}_{market}")
    os.makedirs("output", exist_ok=True)

    caption = extract_caption(script)
    caption_file = f"output/{safe_name}_caption.txt"
    with open(caption_file, "w", encoding="utf-8") as f:
        # ffmpeg drawtext 特殊字符转义
        f.write(caption.replace(":", "\\:").replace("'", "\\'").replace("[", "\\[").replace("]", "\\]"))

    output_file = f"output/{safe_name}.mp4"

    font_path = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    font_opt = f":fontfile={font_path}" if os.path.exists(font_path) else ""

    # 价格标签
    currency = MARKET_CURRENCY.get(Market(market), "£")
    price_text = f"Only {currency}{product.price}"

    vf = (
        # 背景
        f"color=c={bg_color}:s=1080x1920:d=15"
        f",drawtext=text='{price_text}'"
        f":fontsize=52:fontcolor=yellow:x=(w-text_w)/2:y=200"
        f":shadowcolor=black:shadowx=3:shadowy=3{font_opt}"
        f",drawtext=textfile='{caption_file}'"
        f":fontsize=38:fontcolor={font_color}:x=60:y=500"
        f":line_spacing=12:shadowcolor=black:shadowx=2:shadowy=2{font_opt}"
        f",drawtext=text='TikTok Shop':fontsize=28"
        f":fontcolor=white@0.5:x=60:y=1800{font_opt}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        output_file
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
        logger.info(f"🎬 视频生成: {output_file}")
        return output_file
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg 失败:\n{e.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg 超时: {product.title}")


# =========================
# 4. TikTok 上传（集成 TiktokAutoUploader）
# =========================
def upload_to_tiktok(video_path: str, description: str, product: Product) -> dict:
    """
    集成 github.com/makiisthenes/TiktokAutoUploader
    需提前运行: python3 cli.py auth --user your_username
    cookies 存储在 TiktokAutoUploader/VideosDirPath/
    """
    uploader_path = os.getenv("TIKTOK_UPLOADER_PATH", "./TiktokAutoUploader")
    username = os.getenv("TIKTOK_USERNAME", "")

    if not username:
        logger.warning("⚠️ TIKTOK_USERNAME 未设置，跳过上传")
        return {"status": "skipped", "reason": "no username configured"}

    # 复制视频到 uploader 目录
    import shutil
    dest = os.path.join(uploader_path, "VideosDirPath", os.path.basename(video_path))
    shutil.copy2(video_path, dest)

    cmd = [
        "python3", "cli.py", "upload",
        "--user", username,
        "-v", os.path.basename(video_path),
        "-t", description[:150],
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
            cwd=uploader_path
        )
        logger.info(f"📤 TikTok 上传成功: {video_path}")
        return {"status": "uploaded", "output": result.stdout[-200:]}
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ TikTok 上传失败: {e.stderr[-300:]}")
        return {"status": "failed", "error": e.stderr[-300:]}
    except FileNotFoundError:
        logger.warning("⚠️ TiktokAutoUploader 未安装，跳过上传")
        return {"status": "skipped", "reason": "uploader not found"}


# =========================
# 5. 完整流水线
# =========================
def run_pipeline(task_id: str, config: PipelineConfig):
    task_store[task_id] = {"status": "running", "results": [], "error": None}

    try:
        logger.info(f"[{task_id}] 🚀 启动 | 市场:{config.target_market} 最低利润率:{config.min_profit_margin:.0%}")

        products = get_products()
        filtered = filter_products(products, config)

        if not filtered:
            task_store[task_id] = {
                "status": "done",
                "results": [],
                "error": f"[{config.target_market}] 无符合条件商品（利润率>{config.min_profit_margin:.0%} 趋势>{config.min_trend_score}）"
            }
            return

        results = []
        for p in filtered:
            item = {"product": p.title, "category": p.category, "market": config.target_market}
            try:
                # Step 1: 脚本生成
                script = generate_script(p, config)
                item["script_preview"] = script[:150] + "..."

                # Step 2: 视频生成
                video_path = create_video(script, p, config.target_market)
                item["video_path"] = video_path
                item["video_style"] = p.style
                item["profit_margin"] = round((p.price - p.cost) / p.price, 3)

                # Step 3: 上传（可选，需配置 TIKTOK_USERNAME）
                upload_result = upload_to_tiktok(video_path, script[:150], p)
                item["upload"] = upload_result
                item["status"] = "success"

            except Exception as e:
                logger.error(f"[{task_id}] ❌ {p.title} 失败: {e}")
                item["status"] = "failed"
                item["error"] = str(e)

            results.append(item)

        task_store[task_id] = {"status": "done", "results": results, "error": None}
        success_count = sum(1 for r in results if r.get("status") == "success")
        logger.info(f"[{task_id}] ✅ 完成 | 成功:{success_count}/{len(results)}")

    except Exception as e:
        logger.exception(f"[{task_id}] 💥 流水线崩溃: {e}")
        task_store[task_id] = {"status": "failed", "results": [], "error": str(e)}


# =========================
# 6. API 接口
# =========================
@app.get("/", summary="健康检查")
def home():
    return {
        "status": "running",
        "service": "AI Commerce Pro EU v2.0",
        "markets": [m.value for m in Market],
        "product_count": len(EUROPE_PRODUCT_CATALOG),
    }


@app.post("/run", summary="触发流水线（异步）")
def run(background_tasks: BackgroundTasks, config: PipelineConfig = None):
    """
    异步触发流水线，立即返回 task_id。
    
    示例请求体:
    {
        "target_market": "UK",
        "min_profit_margin": 0.60,
        "min_trend_score": 0.85,
        "max_products": 3
    }
    """
    if config is None:
        config = PipelineConfig()

    task_id = str(uuid.uuid4())[:8]
    task_store[task_id] = {"status": "pending"}
    background_tasks.add_task(run_pipeline, task_id, config)
    logger.info(f"📋 任务提交: {task_id} | 市场:{config.target_market}")

    return {
        "task_id": task_id,
        "config": config.model_dump(),
        "message": f"任务已提交，使用 GET /status/{task_id} 查询进度"
    }


@app.get("/status/{task_id}", summary="查询任务状态", response_model=TaskStatus)
def get_status(task_id: str):
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return TaskStatus(task_id=task_id, **task)


@app.get("/tasks", summary="所有任务列表")
def list_tasks():
    return {
        "total": len(task_store),
        "tasks": [{"task_id": tid, "status": v.get("status")} for tid, v in task_store.items()]
    }


@app.get("/products", summary="查看商品库")
def list_products(market: Optional[Market] = None, category: Optional[str] = None):
    """查看欧洲商品库，支持按市场/类目筛选"""
    items = EUROPE_PRODUCT_CATALOG
    if market:
        items = [p for p in items if market.value in p["markets"]]
    if category:
        items = [p for p in items if p["category"].lower() == category.lower()]
    return {"total": len(items), "products": items}


@app.get("/markets", summary="各市场商品统计")
def market_stats():
    stats = {}
    for m in Market:
        market_products = [p for p in EUROPE_PRODUCT_CATALOG if m.value in p["markets"]]
        categories = list(set(p["category"] for p in market_products))
        avg_margin = sum((p["price"] - p["cost"]) / p["price"] for p in market_products) / len(market_products)
        stats[m.value] = {
            "product_count": len(market_products),
            "categories": categories,
            "avg_profit_margin": f"{avg_margin:.0%}"
        }
    return stats
