from .smartstore import SmartStoreCrawler
from .coupang import CoupangCrawler
from .cafe24 import Cafe24Crawler
from .auction import AuctionCrawler
from .gmarket import GmarketCrawler
from .eleven import ElevenCrawler
from .ssg import SSGCrawler

CRAWLERS = {
    "카페24": Cafe24Crawler,
    "스마트스토어": SmartStoreCrawler,
    "쿠팡": CoupangCrawler,
    "옥션": AuctionCrawler,
    "지마켓": GmarketCrawler,
    "11번가": ElevenCrawler,
    "SSG": SSGCrawler,
}
