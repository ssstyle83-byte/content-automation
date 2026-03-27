from .smartstore import SmartStoreCrawler
from .coupang import CoupangCrawler
from .cafe24 import Cafe24Crawler
from .esmplus import ESMPlusCrawler
from .eleven import ElevenCrawler
from .ssg import SSGCrawler

CRAWLERS = {
    "스마트스토어": SmartStoreCrawler,
    "쿠팡": CoupangCrawler,
    "카페24": Cafe24Crawler,
    "ESM플러스": ESMPlusCrawler,
    "11번가": ElevenCrawler,
    "SSG": SSGCrawler,
}
