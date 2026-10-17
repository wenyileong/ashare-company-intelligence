"""Place classification for segments and subsidiaries (v1.2).

``jurisdiction_class`` distinguishes the Mainland, the special
administrative regions, Taiwan, offshore financial centres commonly used
in red-chip and VIE structures, and other foreign jurisdictions. Matching
is by name (Chinese or English); unrecognised places are UNKNOWN rather
than guessed.
"""
from __future__ import annotations

import re

MAINLAND_PROVINCES = (
    "北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建",
    "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
)
MAINLAND_CITIES = (
    "深圳", "广州", "杭州", "南京", "苏州", "成都", "武汉", "西安", "厦门", "青岛", "宁波", "大连", "沈阳", "长沙",
    "郑州", "合肥", "福州", "济南", "昆明", "贵阳", "南宁", "哈尔滨", "长春", "石家庄", "太原", "呼和浩特",
    "乌鲁木齐", "兰州", "西宁", "银川", "拉萨", "海口", "三亚", "南昌", "无锡", "佛山", "东莞", "珠海", "温州",
    "绍兴", "嘉兴", "常州", "南通", "扬州", "烟台", "潍坊", "泉州", "仁怀", "遵义", "宜宾", "泸州", "惠州", "中山",
)
MAINLAND_WORDS = ("中国大陆", "中国境内", "境内", "国内", "内销", "华东", "华北", "华南", "华中", "西南", "西北",
                  "东北", "中国")
OFFSHORE = ("开曼", "Cayman", "英属维尔京", "维尔京", "BVI", "British Virgin", "百慕大", "Bermuda", "萨摩亚", "Samoa",
            "塞舌尔", "Seychelles", "马绍尔", "Marshall", "毛里求斯", "Mauritius", "泽西", "Jersey", "根西", "Guernsey",
            "马恩岛", "Isle of Man", "纳闽", "Labuan", "安圭拉", "Anguilla", "巴哈马", "Bahamas", "巴拿马", "Panama")
HK = ("香港", "Hong Kong", "HK")
MACAU = ("澳门", "Macau", "Macao")
TAIWAN = ("台湾", "Taiwan")
FOREIGN = ("境外", "国外", "海外", "外销", "出口", "其他国家", "新加坡", "Singapore", "美国", "USA", "United States",
           "德国", "Germany", "日本", "Japan", "英国", "United Kingdom", "UK", "法国", "France", "荷兰", "Netherlands",
           "卢森堡", "Luxembourg", "马来西亚", "Malaysia", "印度尼西亚", "印尼", "Indonesia", "越南", "Vietnam",
           "泰国", "Thailand", "澳大利亚", "Australia", "加拿大", "Canada", "韩国", "Korea", "印度", "India", "巴西",
           "Brazil", "墨西哥", "Mexico", "意大利", "Italy", "西班牙", "Spain", "瑞士", "Switzerland", "瑞典",
           "俄罗斯", "Russia", "阿联酋", "UAE", "迪拜", "沙特", "土耳其", "南非", "埃及", "尼日利亚", "以色列",
           "欧洲", "Europe", "美洲", "America", "亚洲", "Asia", "非洲", "Africa", "大洋洲", "中东", "东南亚")


def _has(text: str, words) -> bool:
    for w in words:
        if re.fullmatch(r"[A-Za-z ]+", w):
            if re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", text, re.I):
                return True
        elif w in text:
            return True
    return False


def jurisdiction_class(*places: str | None) -> str | None:
    """MAINLAND / HONG_KONG / MACAU / TAIWAN / OFFSHORE / FOREIGN / UNKNOWN."""
    text = " ".join(p for p in places if p)
    if not text.strip():
        return None
    if _has(text, OFFSHORE):
        return "OFFSHORE"
    if _has(text, HK):
        return "HONG_KONG"
    if _has(text, MACAU):
        return "MACAU"
    if _has(text, TAIWAN):
        return "TAIWAN"
    if _has(text, ("境外", "国外", "海外")) or _has(text, FOREIGN[3:]):
        return "FOREIGN"
    if _has(text, MAINLAND_PROVINCES) or _has(text, MAINLAND_CITIES) or _has(text, MAINLAND_WORDS) \
            or re.search(r"[一-鿿]{1,6}(?:省|市|县|自治区|自治州|新区|开发区)", text):
        return "MAINLAND"
    return "UNKNOWN"


def region_class(segment_name: str) -> str:
    """DOMESTIC / OVERSEAS / UNKNOWN for a regional revenue segment.

    Hong Kong, Macau and Taiwan are classed as OVERSEAS, following the usual
    境内/境外 presentation in A-share annual reports.
    """
    j = jurisdiction_class(segment_name)
    if j == "MAINLAND":
        return "DOMESTIC"
    if j in ("HONG_KONG", "MACAU", "TAIWAN", "OFFSHORE", "FOREIGN"):
        return "OVERSEAS"
    return "UNKNOWN"
