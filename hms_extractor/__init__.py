# -*- coding: utf-8 -*-
from .hms_extractor import HMSExtractor

def classFactory(iface):
    return HMSExtractor(iface)
