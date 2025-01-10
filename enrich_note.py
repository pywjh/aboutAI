# -*- coding: utf-8 -*-
"""
   File Name：     enrich_note
   Author :        bd
   date：          2025/1/6
"""
__author__ = 'bd'

import datetime
import os
import random
import re
from typing import List, Tuple

import requests
from unsplash.api import Api as UnsplashApi
from unsplash.auth import Auth as UnsplashAuth
import httpx
import openai
from dotenv import load_dotenv

load_dotenv()

# 选择要使用的模型
AI_MODEL = "google/gemini-pro"

# OpenRouter configuration
openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
openrouter_app_name = os.getenv('OPENROUTER_APP_NAME', 'video_note_generator')
openrouter_http_referer = os.getenv('OPENROUTER_HTTP_REFERER', 'https://github.com')

# 检查Unsplash配置
unsplash_access_key = os.getenv('UNSPLASH_ACCESS_KEY')
unsplash_client = None

if unsplash_access_key:
    try:
        auth = UnsplashAuth(
            client_id=unsplash_access_key,
            client_secret=None,
            redirect_uri=None
        )
        unsplash_client = UnsplashApi(auth)
        print("✅ Unsplash API 配置成功")
    except Exception as e:
        print(f"❌ Failed to initialize Unsplash client: {str(e)}")

# 配置 OpenAI API
client = openai.OpenAI(
    api_key=openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": openrouter_http_referer,
        "X-Title": openrouter_app_name,
    }
)

openrouter_api_key = os.getenv('OPENROUTER_API_KEY')

if openrouter_api_key:
    try:
        print(f"正在测试 OpenRouter API 连接...")
        response = client.models.list()  # 使用更简单的API调用来测试连接
        print("✅ OpenRouter API 连接测试成功")
        openrouter_available = True
    except Exception as e:
        print(f"⚠️ OpenRouter API 连接测试失败: {str(e)}")
        print("将继续尝试使用API，但可能会遇到问题")


def download_image(image_url, save_path):
    """
    下载图片并保存到本地指定路径
    :param image_url: 图片的URL地址
    :param save_path: 保存图片的路径（包括文件名）
    """
    try:
        # 发送 GET 请求下载图片
        response = requests.get(image_url, stream=True)
        response.raise_for_status()  # 如果请求失败，则抛出异常

        # 打开文件并写入图片内容
        with open(save_path, 'wb') as file:
            for chunk in response.iter_content(1024):
                file.write(chunk)

        print(f"成功下载: {image_url} 到 {save_path}")

    except requests.exceptions.RequestException as e:
        print(f"下载失败: {image_url} 错误信息: {e}")


def download_images_from_urls(image_urls, save_directory):
    """
    根据图片 URL 列表下载所有图片
    :param image_urls: 图片 URL 列表
    :param save_directory: 保存图片的目录
    """
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)  # 如果目录不存在则创建

    for i, image_url in enumerate(image_urls):
        # 构建保存图片的文件路径（图片编号为文件名）
        file_name = f"image_{i + 1}.jpg"  # 你可以根据需要修改文件名后缀
        save_path = os.path.join(save_directory, file_name)

        # 下载并保存图片
        download_image(image_url, save_path)

def split_content(text: str, max_chars: int = 2000) -> List[str]:
    """按段落分割文本，保持上下文的连贯性

    特点：
    1. 保持段落完整性：不会在段落中间断开
    2. 保持句子完整性：确保句子不会被截断
    3. 添加重叠内容：每个chunk都包含上一个chunk的最后一段
    4. 智能分割：对于超长段落，按句子分割并保持完整性
    """
    if not text:
        return []

    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_length = 0
    last_paragraph = None  # 用于存储上一个chunk的最后一段

    for para in paragraphs:
        para = para.strip()
        if not para:  # 跳过空段落
            continue

        para_length = len(para)

        # 如果这是新chunk的开始，且有上一个chunk的最后一段，添加它作为上下文
        if not current_chunk and last_paragraph:
            current_chunk.append(f"上文概要：\n{last_paragraph}\n")
            current_length += len(last_paragraph) + 20  # 加上标题的长度

        # 如果单个段落就超过了最大长度，需要按句子分割
        if para_length > max_chars:
            # 如果当前块不为空，先保存
            if current_chunk:
                last_paragraph = current_chunk[-1]
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_length = 0
                if last_paragraph:
                    current_chunk.append(f"上文概要：\n{last_paragraph}\n")
                    current_length += len(last_paragraph) + 20

            # 按句子分割长段落
            sentences = re.split(r'([。！？])', para)
            current_sentence = []
            current_sentence_length = 0

            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                # 如果有标点符号，加上标点
                if i + 1 < len(sentences):
                    sentence += sentences[i + 1]

                # 如果加上这个句子会超过最大长度，保存当前块并开始新块
                if current_sentence_length + len(sentence) > max_chars and current_sentence:
                    chunks.append(''.join(current_sentence))
                    current_sentence = [sentence]
                    current_sentence_length = len(sentence)
                else:
                    current_sentence.append(sentence)
                    current_sentence_length += len(sentence)

            # 保存最后一个句子块
            if current_sentence:
                chunks.append(''.join(current_sentence))
        else:
            # 如果加上这个段落会超过最大长度，保存当前块并开始新块
            if current_length + para_length > max_chars and current_chunk:
                last_paragraph = current_chunk[-1]
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_length = 0
                if last_paragraph:
                    current_chunk.append(f"上文概要：\n{last_paragraph}\n")
                    current_length += len(last_paragraph) + 20
            current_chunk.append(para)
            current_length += para_length

    # 保存最后一个块
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def _organize_long_content(self, content: str, duration: int = 0) -> str:
    """使用AI整理长文内容"""
    if not content.strip():
        return ""

    if not self.openrouter_available:
        print("⚠️ OpenRouter API 不可用，将返回原始内容")
        return content

    content_chunks = self.split_content(content)
    organized_chunks = []

    print(f"内容将分为 {len(content_chunks)} 个部分进行处理...")

    for i, chunk in enumerate(content_chunks, 1):
        print(f"正在处理第 {i}/{len(content_chunks)} 部分...")
        organized_chunk = self._organize_content(chunk)
        organized_chunks.append(organized_chunk)

    return "\n\n".join(organized_chunks)


def _organize_content(content: str) -> str:
    """使用AI整理内容"""
    try:
        if not openrouter_available:
            print("⚠️ OpenRouter API 未配置，将返回原始内容")
            return content

        # 构建系统提示词
        system_prompt = """你是一位著名的科普作家和博客作者，著作等身，屡获殊荣，尤其在内容创作领域有深厚的造诣。

请使用 4C 模型（建立联系 Connection、展示冲突 Conflict、强调改变 Change、即时收获 Catch）为转录的文字内容创建结构。

写作要求：
- 从用户的问题出发，引导读者理解核心概念及其背景
- 使用第二人称与读者对话，语气亲切平实
- 确保所有观点和内容基于用户提供的转录文本
- 如无具体实例，则不编造
- 涉及复杂逻辑时，使用直观类比
- 避免内容重复冗余
- 逻辑递进清晰，从问题开始，逐步深入

Markdown格式要求：
- 大标题突出主题，吸引眼球，最好使用疑问句
- 小标题简洁有力，结构清晰，尽量使用单词或短语
- 直入主题，在第一部分清晰阐述问题和需求
- 正文使用自然段，避免使用列表形式
- 内容翔实，避免过度简略，特别注意保留原文中的数据和示例信息
- 如有来源URL，使用文内链接形式
- 保留原文中的Markdown格式图片链接"""

        # 构建用户提示词
        final_prompt = f"""请根据以下转录文字内容，创作一篇结构清晰、易于理解的博客文章。

转录文字内容：

{content}"""

        # 调用API
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )

        if response.choices:
            return response.choices[0].message.content.strip()

        return content

    except Exception as e:
        print(f"⚠️ 内容整理失败: {str(e)}")
        return content


def organize_long_content(content: str) -> str:
    """使用AI整理长文内容"""
    if not content.strip():
        return ""

    if not openrouter_available:
        print("⚠️ OpenRouter API 不可用，将返回原始内容")
        return content

    content_chunks = split_content(content)
    organized_chunks = []

    print(f"内容将分为 {len(content_chunks)} 个部分进行处理...")

    for i, chunk in enumerate(content_chunks, 1):
        print(f"正在处理第 {i}/{len(content_chunks)} 部分...")
        organized_chunk = _organize_content(chunk)
        organized_chunks.append(organized_chunk)

    return "\n\n".join(organized_chunks)


def _get_unsplash_images(query: str, count: int = 3) -> List[str]:
    """从Unsplash获取相关图片"""
    if not unsplash_client:
        print("⚠️ Unsplash客户端未初始化")
        return []

    try:
        # 将查询词翻译成英文以获得更好的结果
        if openrouter_available:
            try:
                response = client.chat.completions.create(
                    model=AI_MODEL,
                    messages=[
                        {"role": "system",
                         "content": "你是一个翻译助手。请将输入的中文关键词翻译成最相关的1-3个英文关键词，用逗号分隔。直接返回翻译结果，不要加任何解释。例如：\n输入：'保险理财知识'\n输出：insurance,finance,investment"},
                        {"role": "user", "content": query}
                    ],
                    temperature=0.3,
                    max_tokens=50
                )
                if response.choices:
                    query = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"⚠️ 翻译关键词失败: {str(e)}")

        # 使用httpx直接调用Unsplash API
        headers = {
            'Authorization': f'Client-ID {os.getenv("UNSPLASH_ACCESS_KEY")}'
        }

        # 对每个关键词分别搜索
        all_photos = []
        for keyword in query.split(','):
            response = httpx.get(
                'https://api.unsplash.com/search/photos',
                params={
                    'query': keyword.strip(),
                    'per_page': count,
                    'orientation': 'portrait',  # 小红书偏好竖版图片
                    'content_filter': 'high'  # 只返回高质量图片
                },
                headers=headers,
                verify=False  # 禁用SSL验证
            )

            if response.status_code == 200:
                data = response.json()
                if data['results']:
                    # 获取图片URL，优先使用regular尺寸
                    photos = [photo['urls'].get('regular', photo['urls']['small'])
                              for photo in data['results']]
                    all_photos.extend(photos)

        # 如果收集到的图片不够，用最后一个关键词继续搜索
        while len(all_photos) < count and query:
            response = httpx.get(
                'https://api.unsplash.com/search/photos',
                params={
                    'query': query.split(',')[-1].strip(),
                    'per_page': count - len(all_photos),
                    'orientation': 'portrait',
                    'content_filter': 'high',
                    'page': 2  # 获取下一页的结果
                },
                headers=headers,
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                if data['results']:
                    photos = [photo['urls'].get('regular', photo['urls']['small'])
                              for photo in data['results']]
                    all_photos.extend(photos)
                else:
                    break
            else:
                break

        # 返回指定数量的图片
        download_images_from_urls(all_photos[:10], f'temp_images/{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}')
        return all_photos[:count]

    except Exception as e:
        print(f"⚠️ 获取图片失败: {str(e)}")
        return []


def get_content_titles(content):
    content_lines = content.split('\n')
    titles = []
    for line in content_lines:
        line = line.strip()
        if line and line.startswith('##') and '：' not in line and '。' not in line:
            titles = [line]
            break
    return titles


def convert_to_xiaohongshu(content: str) -> Tuple[str, List[str], List[str], List[str]]:
    """将博客文章转换为小红书风格的笔记，并生成标题和标签"""
    try:
        if not openrouter_available:
            print("⚠️ OpenRouter API 未配置，将返回原始内容")
            return content, [], [], []

        # 构建系统提示词
        system_prompt = """你是一位专业的小红书爆款文案写作大师，擅长将普通内容转换为刷屏级爆款笔记。
请将输入的内容转换为小红书风格的笔记，需要满足以下要求：

1. 标题创作（重要‼️）：
- 二极管标题法：
* 追求快乐：产品/方法 + 只需N秒 + 逆天效果
* 逃避痛苦：不采取行动 + 巨大损失 + 紧迫感
- 爆款关键词（必选1-2个）：
* 高转化词：好用到哭、宝藏、神器、压箱底、隐藏干货、高级感
* 情感词：绝绝子、破防了、治愈、万万没想到、爆款、永远可以相信
* 身份词：小白必看、手残党必备、打工人、普通女生
* 程度词：疯狂点赞、超有料、无敌、一百分、良心推荐
- 标题规则：
* 字数：20字以内
* emoji：2-4个相关表情
* 标点：感叹号、省略号增强表达
* 风格：口语化、制造悬念

2. 正文创作：
- 开篇设置（抓住痛点）：
* 共情开场：描述读者痛点
* 悬念引导：埋下解决方案的伏笔
* 场景还原：具体描述场景
- 内容结构：
* 每段开头用emoji引导
* 重点内容加粗突出
* 适当空行增加可读性
* 步骤说明要清晰
- 写作风格：
* 热情亲切的语气
* 大量使用口语化表达
* 插入互动性问句
* 加入个人经验分享
- 高级技巧：
* 使用平台热梗
* 加入流行口头禅
* 设置悬念和爆点
* 情感共鸣描写

3. 标签优化：
- 提取4类标签（每类1-2个）：
* 形如：#关键词+空格，例如： #关键词1 #关键词2 
* 核心关键词：主题相关
* 关联关键词：长尾词
* 高转化词：购买意向强
* 热搜词：行业热点
* 避免内容冗余重复
* 总计不能超过20

4. 整体要求：
- 内容体量：根据内容自动调整
- 结构清晰：善用分点和空行
- 情感真实：避免过度营销
- 互动引导：设置互动机会
- AI友好：避免机器味
- 不能出现忤逆中国（中华民族共和国），反对中国的言论
- 不能出现对中华民族共和国玩笑的言论

注意：创作时要始终记住，标题决定打开率，内容决定完播率，互动决定涨粉率！"""

        # 构建用户提示词
        user_prompt = f"""请将以下内容转换为爆款小红书笔记。

内容如下：
{content}

请按照以下格式返回：
1. 第一行：爆款标题（遵循二极管标题法，必须有emoji）
2. 空一行
3. 正文内容（注意结构、风格、技巧的运用，控制在600-800字之间）
4. 空一行
5. 标签列表（每类标签都要有，用#号开头）

创作要求：
1. 标题要让人忍不住点进来看
2. 内容要有干货，但表达要轻松
3. 每段都要用emoji装饰
4. 标签要覆盖核心词、关联词、转化词、热搜词
5. 设置2-3处互动引导
6. 通篇要有感情和温度
7. 正文控制在600-800字之间
8. 内容不得包含任何违反平台规定的内容
9. 不要系统提示要求的内容展示出来
"""

        # 调用API
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )

        if not response.choices:
            raise Exception("API 返回结果为空")

        # 处理返回的内容
        xiaohongshu_content = response.choices[0].message.content.strip()
        print(f"\n📝 API返回内容：\n{xiaohongshu_content}\n")

        # 提取标题（第一行）
        titles = get_content_titles(xiaohongshu_content)
        if titles and len(titles[0]) > 50:
            titles = get_content_titles(content)

        if not titles:
            print("⚠️ 未找到标题，尝试其他方式提取...")
            # 尝试其他方式提取标题
            title_match = re.search(r'^[^#\n]+', xiaohongshu_content)
            if title_match:
                titles = [title_match.group(0).strip()]

        if titles:
            print(f"✅ 提取到标题: {titles[0]}")
        else:
            print("⚠️ 未能提取到标题")

        # 提取标签（查找所有#开头的标签）
        tags = []
        # tag_matches = re.findall(r'#、([^\s#]+)', xiaohongshu_content)
        tag_matches = re.findall(r"#([\w\u4e00-\u9fa5]+)", xiaohongshu_content, re.MULTILINE)
        if tag_matches:
            tags = tag_matches
            print(f"✅ 提取到{len(tags)}个标签: {tags}")
        else:
            print("⚠️ 未找到标签")

        # 获取相关图片
        images = []
        if unsplash_client:
            # 使用标题和标签作为搜索关键词
            if len(tags) >= 3:
                search_terms = tags[:3]
            else:
                search_terms = titles + tags[:2]
            search_query = ' '.join(search_terms)
            try:
                images = _get_unsplash_images(search_query, count=4)
                if images:
                    print(f"✅ 成功获取{len(images)}张配图")
                else:
                    print("⚠️ 未找到相关配图")
            except Exception as e:
                print(f"⚠️ 获取配图失败: {str(e)}")

        return xiaohongshu_content, titles, tags, images

    except Exception as e:
        print(f"⚠️ 转换小红书笔记失败: {str(e)}")
        return content, [], [], []


def main(text: str):
    organized_content = organize_long_content(text)
    # 生成小红书版本
    print("\n📱 正在生成小红书版本...")
    try:
        xiaohongshu_content, titles, tags, images = convert_to_xiaohongshu(organized_content)
        # 保存小红书版本
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        xiaohongshu_file = os.path.join("temp_notes", f"{timestamp}_xiaohongshu.md")

        # 写入文件
        with open(xiaohongshu_file, "w", encoding="utf-8") as f:
            # 写入标题 - 如果没有生成的标题就使用视频原标题
            if len(titles) > 0:
                title = titles[0].replace("#", "")
            else:
                title = "小红书笔记"
            f.write(f"# {title}\n\n")

            # 如果有图片，先写入第一张作为封面
            if images:
                f.write(f"![封面图]({images[0]})\n\n")

            # 写入正文内容
            f.write(xiaohongshu_content)

            # 如果有额外的图片，在文章中间和末尾插入
            if len(images) > 1:
                f.write(f"\n\n![配图]({images[1]})")
            if len(images) > 2:
                f.write(f"\n\n![配图]({images[2]})")

            # 写入标签
            if tags:
                f.write("\n\n---\n")
                f.write("\n".join([f"#{tag}" for tag in tags]))

        print(f"\n✅ 小红书版本已保存至: {xiaohongshu_file}")

    except Exception as e:
        print(f"⚠️ 生成小红书版本失败: {str(e)}")
        import traceback
        print(f"错误详情:\n{traceback.format_exc()}")


if __name__ == '__main__':
    text = """
    
        熬夜对健身的影响远比我们通常认识到的表面问题更为深刻。为了理解为什么熬夜会影响健身，我们可以从多个角度来探讨，包括生理学、心理学以及运动生理学等方面的影响。

### 1. **生理学上的影响：**
人体的生理机能在晚上进入修复和恢复模式，尤其是在深度睡眠阶段，体内发生了大量的生理过程。这些过程对于保持体能和促进肌肉生长至关重要。熬夜打乱了这一生理节奏，带来以下几方面的负面影响：

- **荷尔蒙分泌的紊乱：** 睡眠过程中，身体会分泌生长激素，这是促进肌肉修复和生长的关键。熬夜会导致生长激素分泌减少，这直接影响健身效果，尤其是力量训练后的肌肉修复。
- **皮质醇水平升高：** 熬夜会刺激体内皮质醇（一种应激激素）的分泌，皮质醇过高会导致肌肉分解，从而削弱力量训练后的恢复效果。长时间处于这种应激状态中，还可能引起慢性炎症，影响整体健康。
- **免疫系统的功能降低：** 长期熬夜还会影响免疫系统，使身体更容易受到伤害或感染，这对于进行高强度训练的人来说尤其危险。

### 2. **心理学上的影响：**
睡眠不足会对大脑和神经系统产生深远的影响，这些影响不仅体现在情绪和认知能力上，也直接影响健身表现。

- **集中力和动力下降：** 睡眠对大脑的恢复至关重要，熬夜会使你在锻炼时更容易感到疲劳、无法集中精力或失去动力。这种状态下进行健身训练，效果自然大打折扣。
- **疲劳感和心理抗压能力的下降：** 长时间熬夜后，心理的抗压能力和情绪调节能力会下降，这使得训练时面对挑战和压力时容易放弃，导致训练强度下降。

### 3. **运动生理学上的影响：**
从运动生理学的角度来看，身体在高强度训练后的恢复主要依赖于充足的休息，特别是睡眠。如果没有足够的睡眠来支持这一过程，健身效果会受到极大影响：

- **肌肉恢复延迟：** 在训练后，肌肉纤维需要修复，而这一修复过程在深度睡眠中最为高效。熬夜会减少这一阶段的时间，导致肌肉恢复不充分，甚至可能在长期影响下出现过度训练的情况。
- **运动表现降低：** 研究显示，熬夜会影响运动表现，特别是在高强度运动和耐力训练中。睡眠不足的人往往在运动时的心率、力量、反应速度等指标都会受到影响，无法达到最佳状态。

### 4. **长期影响与运动损伤的风险：**
短期内，熬夜可能不会立刻对身体造成不可逆的损伤，但长期熬夜会增加运动损伤的风险：

- **关节和肌肉的耐受性降低：** 睡眠不足会让身体的修复能力下降，训练过程中更容易出现小的伤害，这些小伤害如果不及时修复，可能会导致更大的损伤。
- **运动表现的疲态：** 长期缺乏恢复，身体处于持续的疲劳状态，会让你在运动过程中容易出现动作不规范，姿势不稳定，导致受伤风险增加。

### 5. **神经-肌肉适应性和训练效果的减弱：**
神经系统的适应性在训练过程中非常重要，尤其是在力量训练中，神经系统的适应性决定了力量的提升和动作的精准度。熬夜会影响大脑和神经系统的恢复，使得神经系统的适应能力降低，从而影响到运动的效果。

### 总结：
熬夜不仅会影响健身的直接效果，还会对身体的各个系统造成潜在的长期影响。从生理学、心理学到运动生理学，睡眠的缺乏会妨碍肌肉的恢复、训练表现的提升和运动健康的维持。健康的睡眠不仅是高效健身的基础，更是提升训练效果、避免运动损伤和保持长期健身计划可持续性的关键。因此，要想在健身上取得显著进展，保持规律的作息和充足的睡眠显得尤为重要。
    """
    main(text)
