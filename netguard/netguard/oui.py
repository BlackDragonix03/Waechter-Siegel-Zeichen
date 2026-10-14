"""Hersteller aus der MAC-Adresse (OUI).

Eingebaut ist eine kompakte Liste häufiger Hersteller. Eine vollständige Liste
kann als Datei ``oui.txt`` (IEEE-Format, https://standards-oui.ieee.org/oui/oui.txt)
oder ``manuf`` (Wireshark-Format) in den Datenordner oder neben die Exe gelegt
werden; sie wird beim Start automatisch eingelesen.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Prefix (6 Hex, Großschreibung) -> Hersteller
_BUILTIN: dict[str, str] = {}

_RAW = """
# AVM (Fritz!Box)
001C4A AVM|002A9C AVM|0896D7 AVM|2C3AFD AVM|3810D5 AVM|5C4979 AVM|7CFF4D AVM|C80E14 AVM|D4F6F3 AVM|E0286D AVM|F0B014 AVM|44FE3B AVM|C02506 AVM|98E7F4 AVM|9C6B5F AVM|08BF17 AVM|7CB8A2 AVM|BC0526 AVM|6C7E67 AVM|342D38 AVM|00040E AVM|D82428 AVM
# Telekom / Speedport
D4EC4F Telekom Speedport|5C8E72 Telekom Speedport|F43E61 Telekom Speedport|347A60 Telekom Speedport|C0D16B Telekom Speedport|8CE0D5 Telekom Speedport|C4D8F3 Telekom Speedport
# TP-Link
50C7BF TP-Link|60E327 TP-Link|98DAC4 TP-Link|A42BB0 TP-Link|B0BE76 TP-Link|C006C3 TP-Link|D8074B TP-Link|E8DE27 TP-Link|F4F26D TP-Link|1C3BF3 TP-Link|30DE4B TP-Link|5091E3 TP-Link|54AF97 TP-Link|6CB158 TP-Link|9C53E6 TP-Link|AC84C6 TP-Link|B4B024 TP-Link|CC32E5 TP-Link|E4C32A TP-Link|9C5322 TP-Link|403F8C TP-Link|788CB5 TP-Link|7CC2C6 TP-Link|140DBA TP-Link|3C52A1 TP-Link|482254 TP-Link
# Netgear
20E52A Netgear|2C3033 Netgear|6CB0CE Netgear|9C3DCF Netgear|A040A0 Netgear|B07FB9 Netgear|C40415 Netgear|E0469A Netgear|28C68E Netgear|30469A Netgear|44A56E Netgear|8C3BAD Netgear|A42B8C Netgear|C03F0E Netgear|08028E Netgear|100C6B Netgear|3894ED Netgear
# Ubiquiti
002722 Ubiquiti|0418D6 Ubiquiti|18E829 Ubiquiti|24A43C Ubiquiti|44D9E7 Ubiquiti|687251 Ubiquiti|788A20 Ubiquiti|802AA8 Ubiquiti|B4FBE4 Ubiquiti|DC9FDB Ubiquiti|E063DA Ubiquiti|F09FC2 Ubiquiti|FCECDA Ubiquiti|D021F9 Ubiquiti|7483C2 Ubiquiti|245A4C Ubiquiti|60220C Ubiquiti|9C05D6 Ubiquiti|E4386D Ubiquiti|F492BF Ubiquiti|28704E Ubiquiti|AC8BA9 Ubiquiti
# Cisco / Meraki / Linksys
0CF5A4 Cisco|00000C Cisco|001A2F Cisco|00E0F9 Cisco|5C5015 Cisco|6C9CED Cisco|F8A5C5 Cisco|0018B9 Cisco|00259C Cisco Linksys|001839 Cisco Linksys|0C8268 Cisco Meraki|E0553D Cisco Meraki|88158D Cisco Meraki|AC17C8 Cisco Meraki|C4E90A Linksys|48F8B3 Linksys|14916D Linksys|20AA4B Linksys|586D8F Linksys|C0C1C0 Linksys|E89F80 Linksys|2CFDA1 Linksys
# MikroTik
000C42 MikroTik|4C5E0C MikroTik|6C3B6B MikroTik|744D28 MikroTik|B869F4 MikroTik|C4AD34 MikroTik|CC2DE0 MikroTik|D4CA6D MikroTik|DC2C6E MikroTik|E48D8C MikroTik|2CC81B MikroTik|08551D MikroTik|181E78 MikroTik|48A98A MikroTik|78 9A18 MikroTik
# ASUS
04D4C4 ASUS|08606E ASUS|1C872C ASUS|2C4D54 ASUS|30 5A3A ASUS|50465D ASUS|54040B ASUS|704D7B ASUS|74D02B ASUS|9C5C8E ASUS|AC220B ASUS|B06EBF ASUS|BCEE7B ASUS|D45D64 ASUS|F832E4 ASUS|FCC233 ASUS|10BF48 ASUS|1831BF ASUS|2CFDA1 ASUS|3C7C3F ASUS|4CEDFB ASUS|7C10C9 ASUS|E0D55E ASUS|F02F74 ASUS|244BFE ASUS|485B39 ASUS|A85E45 ASUS|C87F54 ASUS|D017C2 ASUS
# D-Link / Zyxel / Huawei / ZTE / Sagemcom / Arcadyan / Vodafone
1CBDB9 D-Link|14D64D D-Link|28107B D-Link|340804 D-Link|5CD998 D-Link|78542E D-Link|84C9B2 D-Link|9094E4 D-Link|B8A386 D-Link|C8BE19 D-Link|CCB255 D-Link|F0B4D2 D-Link|0015E9 D-Link|001CF0 D-Link|00195B D-Link|001E58 D-Link|002191 D-Link|0022B0 D-Link|0024 01 D-Link|00265A D-Link|0050BA D-Link|1C7EE5 D-Link|A0AB1B D-Link|E46F13 D-Link|ECADE0 D-Link
0013 49 Zyxel|001349 Zyxel|00A0C5 Zyxel|40B089 Zyxel|5CE28C Zyxel|B8ECA3 Zyxel|CC5D4E Zyxel|D8ECE5 Zyxel|E0C6D6 Zyxel|F06E0B Zyxel|2C0FAF Zyxel|4C9EFF Zyxel|90EFC6 Zyxel|A8B8E0 Zyxel|B0B2DC Zyxel|E4188A Zyxel
001E10 Huawei|00259E Huawei|00E0FC Huawei|04C06F Huawei|0819A6 Huawei|101B54 Huawei|20F3A3 Huawei|283CE4 Huawei|30D17E Huawei|48AD08 Huawei|4CB16C Huawei|5C7D5E Huawei|6416F0 Huawei|70723C Huawei|80FB06 Huawei|88E3AB Huawei|8CEBC6 Huawei|AC4E91 Huawei|C8D15E Huawei|D46AA8 Huawei|E0247F Huawei|F4C714 Huawei|00464B Huawei|04BD70 Huawei|109E3A Huawei|18DED7 Huawei|24DF6A Huawei|3CF808 Huawei|4CFB45 Huawei|A47174 Huawei|C40683 Huawei|F83DFF Huawei
001E73 ZTE|0019C6 ZTE|002293 ZTE|00259E ZTE|30F31D ZTE|34E0CF ZTE|4CAC0A ZTE|68DBF5 ZTE|8C E117 ZTE|9CA5C0 ZTE|B075D5 ZTE|C864C7 ZTE|CC7B35 ZTE|D0154A ZTE|F41F88 ZTE|FC2D5E ZTE|00 15EB ZTE|04 95E6 ZTE|2CB57B ZTE|38 46 08 ZTE|6CA75F ZTE|7C7E 6D ZTE
0007 E9 Sagemcom|10D38A Sagemcom|18A6F7 Sagemcom|1C0B52 Sagemcom|2C3996 Sagemcom|3C2C94 Sagemcom|44 D4 54 Sagemcom|504EDC Sagemcom|7C03D8 Sagemcom|A0F2B2 Sagemcom|B0C2 87 Sagemcom|D8 BC6D Sagemcom|E8ADA6 Sagemcom|F42B48 Sagemcom|40F201 Sagemcom|34 2C C4 Sagemcom
001A2A Arcadyan|1C5F2B Arcadyan|50 7E5D Arcadyan|74 31 70 Arcadyan|88252C Arcadyan|8CFABA Arcadyan|A4A4D3 Arcadyan|C4 A9 8F Arcadyan|E4C2D1 Arcadyan|F8B3 2B Arcadyan|2C9D1E Arcadyan|30 F7 72 Arcadyan|B8FF6F Arcadyan|B0 8D 57 Arcadyan|38 C3 F5 Arcadyan|48 5D 36 Arcadyan|00 26 4D Arcadyan|00 23 08 Arcadyan|00 1D 19 Arcadyan|00 12 BF Arcadyan|7C 8A E1 Arcadyan|FC 83 99 Arcadyan|14 AB F0 Arcadyan|48 D3 43 Arcadyan|F4 47 2A Arcadyan|6C 7F B0 Arcadyan|A4 91 B1 Arcadyan|18 83 BF Arcadyan|2C B0 5D Arcadyan|AC E2 D3 Arcadyan|2C D6 42 Arcadyan|7C 05 07 Arcadyan|C0 35 32 Arcadyan|AC 3B 77 Arcadyan|84 8B CD Arcadyan|CC 1A FA Arcadyan|E4 E0 C5 Arcadyan|00 1D 6A Arcadyan|AC E4 B5 Arcadyan|50 E0 85 Arcadyan|D8 8C 79 Arcadyan|60 92 F5 Arcadyan|74 4D 28 Arcadyan|C8 E2 65 Arcadyan|F8 E4 3B Arcadyan|B8 61 F8 Arcadyan|A4 E2 6A Arcadyan|20 B0 01 Arcadyan|AC 9A 22 Arcadyan|10 13 31 Arcadyan|18 E8 29 Arcadyan|4C 09 D4 Arcadyan|6C 33 A9 Arcadyan|1C 24 CD Arcadyan|50 0F F5 Arcadyan|D4 6E 0E Arcadyan|78 CA 39 Arcadyan|E0 60 66 Arcadyan|C0 E4 2D Arcadyan|B4 9E AC Arcadyan|94 A6 7E Arcadyan|B8 55 10 Arcadyan|58 D9 D5 Arcadyan|B0 E8 92 Arcadyan|90 72 40 Arcadyan|6C B4 FD Arcadyan|B0 C5 54 Arcadyan|70 B3 D5 Arcadyan|A4 6C F1 Arcadyan|00 1F 2E Arcadyan|00 E0 4C Arcadyan|EC 08 6B Arcadyan|FC 7F F1 Arcadyan|00 1B 32 Arcadyan|B4 A7 C6 Arcadyan|00 11 50 Arcadyan|E8 FC AF Arcadyan|B8 E2 63 Arcadyan|60 8D 26 Arcadyan|44 11 29 Arcadyan|6C 5A B0 Arcadyan|84 2A FD Arcadyan|8C 9D 1E Arcadyan|00 0C E5 Arcadyan|40 6A AB Arcadyan|2C F4 C5 Arcadyan|60 D7 55 Arcadyan|E0 B6 F5 Arcadyan|C4 A1 51 Arcadyan|EC 71 DB Arcadyan|90 2E 16 Arcadyan|28 9A FA Arcadyan|AC 33 28 Arcadyan|6C C2 17 Arcadyan|34 E3 80 Arcadyan|FC E6 6A Arcadyan|B8 D5 26 Arcadyan|1C 3A DE Arcadyan|B8 4D 43 Arcadyan|DC FB 48 Arcadyan|F0 D2 F1 Arcadyan|D0 65 CA Arcadyan|78 D8 00 Arcadyan|44 05 3F Arcadyan|B8 4A D8 Arcadyan|EC 4D 3E Arcadyan|CC 7B 5C Arcadyan|B4 2D 56 Arcadyan|40 BB CB Arcadyan|34 25 BB Arcadyan|50 1C B0 Arcadyan|00 1A 70 Arcadyan|B4 F5 0A Arcadyan|1C E8 9E Arcadyan|9C 1A 50 Arcadyan|FC A0 C5 Arcadyan|D4 1A 3F Arcadyan|AC AB 8D Arcadyan|94 0C 6D Arcadyan|98 1F 3C Arcadyan|74 7D 24 Arcadyan|C8 32 A9 Arcadyan|E8 8D 28 Arcadyan|48 71 C2 Arcadyan|A0 E5 E9 Arcadyan|D8 9A 34 Arcadyan|3C D0 E4 Arcadyan|B8 1E A4 Arcadyan|AC 32 8F Arcadyan|DC 6D CD Arcadyan|A4 11 62 Arcadyan|18 5C 4A Arcadyan|2C 29 97 Arcadyan|AC 84 C9 Arcadyan|24 F5 A2 Arcadyan|7C 8B 3C Arcadyan|80 20 FD Arcadyan|B8 94 94 Arcadyan|D4 5A 1F Arcadyan|B0 B6 6C Arcadyan|CC 9E A2 Arcadyan|D4 6E 5C Arcadyan|B0 48 7A Arcadyan|98 FC 11 Arcadyan|FC C4 E8 Arcadyan|E0 A4 D4 Arcadyan
# Vodafone / Unitymedia / Kabel (Compal, Technicolor, Hitron, Sercomm)
0C9D92 Vodafone (Arris)|3C7A8A Vodafone (Arris)|6C5AB5 Vodafone (Arris)|A4ED4E Vodafone (Arris)|90C792 Compal|C086D2 Compal|8CBF E6 Compal|B0 6A41 Compal|0C 8C24 Compal|E4F4C6 Compal|1C1448 Technicolor|FC9465 Technicolor|AC84C9 Technicolor|7CBFB1 Technicolor|90BDB0 Technicolor|F0 F2 49 Technicolor|E0B7B1 Technicolor|88D7F6 Technicolor|20B001 Technicolor|E0A4D4 Technicolor|D4B27A Technicolor|7C 4F B5 Arris|00 1D CF Arris|00 23 ED Arris|38 3B C8 Arris|60 8F 5C Arris|90 1A CA Arris|E8 6D 52 Arris|94 CC B9 Arris|F8 8B 37 Arris|FC 51 A4 Arris|68 1A B2 Arris|C0 05 C2 Arris|A4 4C C8 Arris|BC 64 4B Arris|44 32 C8 Arris|D4 3F CB Arris|3C 36 E4 Arris|34 6B 46 Hitron|68 1B EB Hitron|8C 90 D3 Hitron|D8 1D 72 Hitron|00 1E 7C Hitron|00 10 5D Hitron|0C 15 C5 Sercomm|00 0E 56 Sercomm|9C 94 A8 Sercomm|C4 71 FE Sercomm|00 24 FD Sercomm|E0 5F 45 Sercomm|8C 4D EA Sercomm|20 C0 47 Sercomm
# Apple
000393 Apple|0016CB Apple|001EC2 Apple|002332 Apple|0025BC Apple|0026BB Apple|003EE1 Apple|0C4DE9 Apple|109ADD Apple|14109F Apple|183451 Apple|1C36BB Apple|28CFE9 Apple|3C0754 Apple|40A6D9 Apple|4C8D79 Apple|5C5948 Apple|60F81D Apple|64B9E8 Apple|6C709F Apple|70CD60 Apple|7C6D62 Apple|8C8590 Apple|9803D8 Apple|A45E60 Apple|A85C2C Apple|AC87A3 Apple|B065BD Apple|B8E856 Apple|BC5436 Apple|C82A14 Apple|D0E140 Apple|DC2B2A Apple|E0B52D Apple|F0DBE2 Apple|F4F15A Apple|F82793 Apple|3C2EFF Apple|34363B Apple|F0D1A9 Apple|A4D1D2 Apple|D4619D Apple|78D75F Apple|F02475 Apple|38C986 Apple|04D3CF Apple|CC08E0 Apple|0C7418 Apple|B0CA68 Apple|1C57DC Apple|B8098A Apple|50EAD6 Apple|E4E4AB Apple|9CF48E Apple|DCA4CA Apple|2CBE08 Apple|E425E7 Apple|BC9FEF Apple|1CABA7 Apple|7CD1C3 Apple|A4C361 Apple|88E9FE Apple|6C4D73 Apple|20A2E4 Apple|F86FC1 Apple|C4B301 Apple|E8802E Apple|4C3275 Apple|8C7C92 Apple|9C35EB Apple|C06394 Apple|3451C9 Apple|A860B6 Apple|E0C767 Apple|F0B479 Apple|B4F0AB Apple|D8D1CB Apple|2C1F23 Apple|D4A33D Apple|145A05 Apple|B8C75D Apple|E4CE8F Apple|B8F6B1 Apple|40B395 Apple|D02B20 Apple|C8334B Apple|6C94F8 Apple|283737 Apple|F4D488 Apple|18AF8F Apple|34A395 Apple|F0989D Apple|9CFC01 Apple|60F445 Apple|A0999B Apple|B853AC Apple|E0F847 Apple|48E9F1 Apple|D4F46F Apple|A8667F Apple|E8B2AC Apple|1C9148 Apple|A0D795 Apple|F4060D Apple|90B21F Apple|AC1F74 Apple|40CBC0 Apple|0050E4 Apple|58B035 Apple|A0ED CD Apple
# Samsung
0007AB Samsung|001247 Samsung|001599 Samsung|0021D1 Samsung|002454 Samsung|0026 37 Samsung|08D42B Samsung|0C715D Samsung|10D542 Samsung|18 3A2D Samsung|1C62B8 Samsung|20D390 Samsung|2C4401 Samsung|3423BA Samsung|38AA3C Samsung|3C5A37 Samsung|40 0E85 Samsung|4C3C16 Samsung|50 01BB Samsung|5C 0A5B Samsung|6411 DD Samsung|6C2F2C Samsung|78 471D Samsung|7C 6193 Samsung|8425DB Samsung|8C 71F8 Samsung|9401C2 Samsung|9C 3AAF Samsung|A0 0BBA Samsung|A8 F274 Samsung|AC 5F3E Samsung|B4 7986 Samsung|B8 5A73 Samsung|BC 20A4 Samsung|C0 BDD1 Samsung|C8 7E75 Samsung|CC 07AB Samsung|D0 176A Samsung|D8 5B2A Samsung|E4 7CF9 Samsung|E8 E5D6 Samsung|F0 25B7 Samsung|F4 7B5E Samsung|FC A13E Samsung|8C F5A3 Samsung|00 1632 Samsung|D4 8890 Samsung|0C 8910 Samsung|34 BE00 Samsung|C4 731E Samsung|2C AE2B Samsung|8C C8CD Samsung|F0 E77E Samsung|E8 3A12 Samsung|44 4E1A Samsung|5C 497D Samsung|1C AF05 Samsung|D0 C24E Samsung|BC 7256 Samsung|50 B7C3 Samsung|78 BDBC Samsung|88 9B39 Samsung|A4 0801 Samsung|98 52B1 Samsung|CC 2D83 Samsung|30 CBF8 Samsung|7C F854 Samsung|84 A466 Samsung|AC C33A Samsung|E0 DB10 Samsung|D4 E8B2 Samsung
# Xiaomi / Huawei Phones / OnePlus / Google / Amazon / Sonos / Philips
28 6C07 Xiaomi|3480B3 Xiaomi|4C49E3 Xiaomi|5056 8E Xiaomi|64 09 80 Xiaomi|64B473 Xiaomi|7C1DD9 Xiaomi|8CBEBE Xiaomi|98FAE3 Xiaomi|9C99A0 Xiaomi|A086C6 Xiaomi|AC F7F3 Xiaomi|B0E235 Xiaomi|C40BCB Xiaomi|D4970B Xiaomi|F0B429 Xiaomi|F48B32 Xiaomi|FC64BA Xiaomi|00 9EC8 Xiaomi|04CF8C Xiaomi|0C1DAF Xiaomi|103420 Xiaomi|142D27 Xiaomi|185F4D Xiaomi|20A783 Xiaomi|286C07 Xiaomi|2CBEB0 Xiaomi|3C BD3E Xiaomi|40 31 3C Xiaomi|44 23 7C Xiaomi|50 EC 50 Xiaomi|58 44 98 Xiaomi|5C E5 0C Xiaomi|60 AB 67 Xiaomi|68 DF DD Xiaomi|74 23 44 Xiaomi|78 11 DC Xiaomi|78 02 F8 Xiaomi|8C 53 C3 Xiaomi|A4 50 46 Xiaomi|B4 A6 1C Xiaomi|C8 C8 4B Xiaomi|D8 3F D4 Xiaomi|E8 6A 64 Xiaomi|EC 9A 5A Xiaomi|F4 F5 DB Xiaomi|FC 29 F3 Xiaomi
3C3AAC OnePlus|94 65 2D OnePlus|C0EEFB OnePlus|A4 E4 B8 OnePlus|64 A2 F9 OnePlus
3C5AB4 Google|54 60 09 Google|94EB2C Google|A47733 Google|F4F5D8 Google|F4F5E8 Google|F88FCA Google|1C F2 9A Google|20DF B9 Google|30 FD 38 Google|48 D6 D5 Google|6C AD F8 Google|E4 F0 42 Google|98 D2 93 Google|CC F4 11 Google|D8 6C 63 Google|D4 F5 47 Google|FC 42 3B Google|00 1A 11 Google|1C A3 B4 Google|F8 0F F9 Google|B0 68 E6 Google
0C47C9 Amazon|10AE60 Amazon|18742E Amazon|34D270 Amazon|38F73D Amazon|40B4CD Amazon|44650D Amazon|4CEFC0 Amazon|50DCE7 Amazon|68 37E9 Amazon|6C5697 Amazon|74C246 Amazon|78E103 Amazon|84D6D0 Amazon|8871E5 Amazon|A002DC Amazon|AC63BE Amazon|B47C9C Amazon|F0272D Amazon|F0F0A4 Amazon|FC65DE Amazon|FCA183 Amazon|0CEE99 Amazon|1C12B0 Amazon|24 4CE3 Amazon|2CF7F1 Amazon|30 4D 92 Amazon|48 9B 46 Amazon|4C 17 44 Amazon|54 61 38 Amazon|58 DF 7E Amazon|60 50 38 Amazon|6C 0C 9A Amazon|90 F1 AA Amazon|90 A8 22 Amazon|94 76 B7 Amazon|A8 E6 21 Amazon|B0 CC 3C Amazon|B0 FC 0D Amazon|C0 94 DC Amazon|C8 D6 CB Amazon|D8 0F 99 Amazon|DC 03 BC Amazon|DC 54 D7 Amazon|E8 6B 56 Amazon|EC 21 23 Amazon|F4 D2 94 Amazon|08 84 9D Amazon|0C 3B 50 Amazon|28 A6 DB Amazon|08 C2 24 Amazon|04 D0 9A Amazon|98 22 EF Amazon
000E58 Sonos|5CAAFD Sonos|949F3E Sonos|B8E937 Sonos|347E5C Sonos|48A6B8 Sonos|542A1B Sonos|78 28 CA Sonos|F0F6C1 Sonos|10 7D 1A Sonos
0017 88 Philips Hue|001788 Philips Hue|ECB5FA Philips Hue|00 0E 4B Philips|70AF24 Philips|9C0A4B Philips|B4D5 BD Philips TV|78 B0 6A Philips TV|D4 CF F9 Philips TV
# Raspberry Pi / IoT
B827EB Raspberry Pi|DCA632 Raspberry Pi|E45F01 Raspberry Pi|28CDC1 Raspberry Pi|D83ADD Raspberry Pi|2CCF67 Raspberry Pi|88A29E Raspberry Pi|3C E1 6F Raspberry Pi
18FE34 Espressif (ESP8266/ESP32)|24 0AC4 Espressif|2462AB Espressif|246F28 Espressif|30AEA4 Espressif|3C71BF Espressif|5CCF7F Espressif|600194 Espressif|68C63A Espressif|807D3A Espressif|84 0D8E Espressif|84CCA8 Espressif|84F3EB Espressif|8CAAB5 Espressif|98F4AB Espressif|A020A6 Espressif|A4CF12 Espressif|AC D074 Espressif|B4E62D Espressif|BCDDC2 Espressif|C44F33 Espressif|C8C9A3 Espressif|CC50E3 Espressif|D8A01D Espressif|DC4F22 Espressif|E8DB84 Espressif|EC FABC Espressif|F4CFA2 Espressif|FCF5C4 Espressif|A4 7B 9D Espressif|0C B8 15 Espressif|10 52 1C Espressif|24 6F 28 Espressif|34 86 5D Espressif|34 94 54 Espressif|40 22 D8 Espressif|40 91 51 Espressif|48 3F DA Espressif|4C 11 AE Espressif|50 02 91 Espressif|54 43 B2 Espressif|58 BF 25 Espressif|78 21 84 Espressif|7C 9E BD Espressif|7C DF A1 Espressif|8C 4B 14 Espressif|94 B9 7E Espressif|9C 9C 1F Espressif|A0 76 4E Espressif|AC 67 B2 Espressif|B8 D6 1A Espressif|C4 4F 33 Espressif|C4 DD 57 Espressif|D4 D4 DA Espressif|E0 98 06 Espressif|E8 68 E7 Espressif|F0 08 D1 Espressif|F4 12 FA Espressif|E8 6B EA Espressif|08 3A F2 Espressif|08 B6 1F Espressif|0C DC 7E Espressif|24 D7 EB Espressif|30 83 98 Espressif|34 B4 72 Espressif|3C 61 05 Espressif|44 17 93 Espressif|48 55 19 Espressif|48 E7 29 Espressif|4C 75 25 Espressif|58 CF 79 Espressif|64 B7 08 Espressif|68 B6 B3 Espressif|70 04 1D Espressif|7C 87 CE Espressif|80 64 6F Espressif|84 FC E6 Espressif|90 38 0C Espressif|94 3C C6 Espressif|A8 03 2A Espressif|A8 42 E3 Espressif|AC 0B FB Espressif|B0 A7 32 Espressif|B4 8A 0A Espressif|C0 49 EF Espressif|C8 2B 96 Espressif|C8 F0 9E Espressif|CC DB A7 Espressif|D4 8A FC Espressif|D8 BF C0 Espressif|DC 54 75 Espressif|E0 5A 1B Espressif|E8 9F 6D Espressif|EC 62 60 Espressif|EC 64 C9 Espressif|F0 9E 9E Espressif|F4 65 0B Espressif|FC B4 67 Espressif
A4 CF12 Shelly (Espressif)|D8BFC0 Shelly|B0 A7 32 Shelly|2C BC BB Tuya|D8 1F 12 Tuya|10 5A 17 Tuya|7C F6 66 Tuya|84 E3 42 Tuya|C8 2E 47 Tuya|D4 A6 51 Tuya|CC 8C BF Tuya|1C 90 FF Tuya|50 8A 06 Tuya|18 DE 50 Tuya
# PC-Hersteller / Netzwerkkarten
000C29 VMware|005056 VMware|001C14 VMware|000569 VMware|00155D Microsoft Hyper-V|0003FF Microsoft|7CED8D Microsoft|28 18 78 Microsoft|BC83 85 Microsoft (Surface)|58 82 A8 Microsoft|98 5F D3 Microsoft Xbox|60 45 BD Microsoft Xbox|7C 1E 52 Microsoft Xbox|C8 3F 26 Microsoft Xbox|9C AA 1B Microsoft|0C 37 96 Microsoft|00 50 F2 Microsoft|08 00 27 VirtualBox|52 54 00 QEMU/KVM|00 16 3E Xen|02 42 AC Docker|00 1C 42 Parallels
3C970E Intel|001B21 Intel|0013CE Intel|8086F2 Intel|00 1E64 Intel|001F3C Intel|002170 Intel|0022FB Intel|0024D6 Intel|0026C7 Intel|3497F6 Intel|4C 8093 Intel|5C514F Intel|7C7A91 Intel|8C705A Intel|A0A8CD Intel|A4C494 Intel|B4B676 Intel|C8F750 Intel|D0 C637 Intel|E4F89C Intel|F8634F Intel|00 2B67 Intel|34E6AD Intel|4CEB42 Intel|5CE0C5 Intel|606720 Intel|80 86F2 Intel|A0510B Intel|B46BFC Intel|B8 8A60 Intel|DC 7196 Intel|E8 2A44 Intel|F0 D5BF Intel|18 1DEA Intel|18 56 80 Intel|28 D0 EA Intel|3C 6A A7 Intel|48 51 C5 Intel|50 E0 85 Intel|58 96 1D Intel|60 DD 8E Intel|6C 88 14 Intel|74 D8 3E Intel|80 19 34 Intel|84 3A 4B Intel|8C 8D 28 Intel|98 8D 46 Intel|9C B6 D0 Intel|A4 34 D9 Intel|AC 12 03 Intel|B0 DC EF Intel|C0 3C 59 Intel|CC 2F 71 Intel|D4 D2 52 Intel|DC 41 A9 Intel|E0 2B E9 Intel|E4 A8 DF Intel|EC 5C 68 Intel|F4 06 69 Intel|F8 E4 E3 Intel|FC 44 82 Intel
00E04C Realtek|52 54 4C Realtek|00 1C 8A Realtek
001B11 D-Link (Realtek)|00248C ASUS (Realtek)|1C6F65 Gigabyte|50E549 Gigabyte|74D435 Gigabyte|E0D55E Gigabyte|B42E99 Gigabyte|18 C0 4D Gigabyte|94DE80 Gigabyte|FC 34 97 Gigabyte|D8 5E D3 Gigabyte|40 B0 76 ASUS|D0 50 99 ASRock|70 85 C2 ASRock|A8 A1 59 ASRock|BC 5F F4 ASRock|8C 89 A5 MSI|D8 BB C1 MSI|00 D8 61 MSI|04 D9 F5 MSI|2C F0 5D MSI|30 9C 23 MSI|4C CC 6A MSI
D4BED9 Dell|F8BC12 Dell|B8CA3A Dell|18DBF2 Dell|5CF9DD Dell|28F10E Dell|34 17EB Dell|489EBD Dell|D89EF3 Dell|E4B97A Dell|00 1AA0 Dell|00 219B Dell|00 2564 Dell|14FEB5 Dell|18 03 73 Dell|1C 40 24 Dell|24 B6 FD Dell|54 BF 64 Dell|6C 2B 59 Dell|8C EC 4B Dell|A4 BB 6D Dell|B0 83 FE Dell|C8 1F 66 Dell|E4 54 E8 Dell|F0 1F AF Dell|F4 02 70 Dell|B4 45 06 Dell|D0 94 66 Dell|00 14 22 Dell|00 1E C9 Dell|00 23 AE Dell|00 24 E8 Dell|00 26 B9 Dell|10 7D 1A Dell|50 9A 4C Dell|74 86 7A Dell|78 2B CB Dell|98 90 96 Dell|98 40 BB Dell|C4 5A B1 Dell
3C D9 2B HP|001F29 HP|0022 64 HP|002481 HP|0025B3 HP|00306E HP|2C27D7 HP|30 8D99 HP|6CC217 HP|80C16E HP|94 57A5 HP|A0D3C1 HP|A0 B3CC HP|B499BA HP|D0BF9C HP|E4115B HP|EC 8EB5 HP|F0921C HP|FC3FDB HP|10 1F74 HP|1458D0 HP|18 A905 HP|1C C1DE HP|28 92 4A HP|34 64 A9 HP|38 63 BB HP|3C A8 2A HP|48 0F CF HP|5C B9 01 HP|64 51 06 HP|70 5A 0F HP|80 CE 62 HP|84 34 97 HP|98 E7 F4 HP|9C 8E 99 HP|A4 5D 36 HP|AC E2 D3 HP|B0 5A DA HP|B4 B5 2F HP|C8 CB B8 HP|D4 85 64 HP|D8 9D 67 HP|DC 4A 3E HP|E8 39 35 HP|EC B1 D7 HP|F4 30 B9 HP|F4 CE 46 HP|40 A8 F0 HP|8C DC D4 HP|00 1B 78 HP|00 17 A4 HP|00 1E 0B HP|00 21 5A HP|00 23 7D HP|00 26 55 HP|00 0F 61 HP|00 11 0A HP|00 12 79 HP|00 14 38 HP|00 14 C2 HP|00 15 60 HP|00 16 35 HP|00 17 08 HP|00 18 FE HP|00 19 BB HP|00 1A 4B HP|00 1C C4 HP|00 1F 28 HP|00 21 5A HP|00 22 64 HP|00 23 7D HP|00 24 81 HP|00 25 B3 HP|00 26 55 HP|00 30 C1 HP|00 60 B0 HP|00 80 5F HP|08 00 09 HP|10 60 4B HP|1C 98 EC HP|24 BE 05 HP|2C 23 3A HP|2C 41 38 HP|2C 44 FD HP|2C 59 E5 HP|2C 76 8A HP|30 E1 71 HP|34 FC B9 HP|3C 4A 92 HP|3C D9 2B HP|40 B0 34 HP|44 1E A1 HP|44 31 92 HP|48 0F CF HP|48 DF 37 HP|5C 8A 38 HP|6C 3B E5 HP|6C C2 17 HP|78 48 59 HP|78 AC C0 HP|78 E3 B5 HP|78 E7 D1 HP|80 C1 6E HP|80 E8 2C HP|84 2B 2B HP|88 51 FB HP|8C DC D4 HP|94 3F C2 HP|98 4B E1 HP|9C 8E 99 HP|9C B6 54 HP|A0 1D 48 HP|A0 2B B8 HP|A0 48 1C HP|A0 8C FD HP|A0 B3 CC HP|A0 D3 C1 HP|A4 5D 36 HP|B4 99 BA HP|B4 B6 86 HP|C4 34 6B HP|C8 CB B8 HP|C8 D3 FF HP|CC 3E 5F HP|D0 7E 28 HP|D0 BF 9C HP|D4 C9 EF HP|D8 94 03 HP|D8 D3 85 HP|DC 4A 3E HP|E0 07 1B HP|E4 11 5B HP|E8 39 35 HP|EC 9A 74 HP|F0 62 81 HP|F0 92 1C HP|F4 03 43 HP|F4 CE 46 HP|FC 15 B4 HP|FC 3F DB HP
00 1E 8F Canon|00 BB C1 Canon|18 0C AC Canon|2C 9E FC Canon|34 CD BE Canon|60 12 8B Canon|88 87 17 Canon|F4 A9 97 Canon|00 1E 8F Canon|04 B1 A1 Canon|30 1A 28 Canon|D8 49 2F Canon|F8 0D 60 Canon|3C D1 6E Canon|B4 7E 8B Canon|34 A0 9E Canon|D0 C1 93 Canon|00 1F 5B Canon
00 1B A9 Brother|00 80 77 Brother|30 05 5C Brother|3C 2A F4 Brother|40 54 E4 Brother|60 B8 0E Brother|00 26 E4 Brother|00 2F 8F Brother|00 1B A9 Brother|8C 9F 6F Brother|E8 F5 97 Brother|9C 50 D1 Brother|F8 9E 4A Brother|9C 7B EF Brother
00 00 48 Epson|00 26 AB Epson|64 EB 8C Epson|A4 EE 57 Epson|AC 18 26 Epson|E8 AB FA Epson|E4 E1 30 Epson|D8 D7 E3 Epson|9C AE D3 Epson|38 9D 92 Epson|44 D2 44 Epson|E8 D9 C3 Epson
00 80 91 Kyocera|00 C0 EE Kyocera|30 F3 1D Kyocera|00 17 C8 Kyocera|00 1F 9B Kyocera|AC F9 70 Kyocera|E8 D7 C2 Kyocera|4C F2 BF Kyocera
00 00 74 Ricoh|00 26 73 Ricoh|58 38 79 Ricoh|60 32 B1 Ricoh|D4 F0 5B Ricoh|00 12 E7 Ricoh|B4 A3 82 Ricoh|D8 B3 C9 Ricoh
00 1E 5E Lexmark|00 20 00 Lexmark|00 21 B7 Lexmark|00 04 00 Lexmark|00 10 83 Lexmark|04 0A 0A Lexmark
00 00 AA Xerox|9C 93 4E Xerox|00 00 00 Xerox|00 00 01 Xerox|00 00 02 Xerox|9C 1C 12 Xerox|00 07 25 Xerox|00 C0 97 Xerox
# NAS
001132 Synology|0011 32 Synology|00 11 32 Synology|90 09 D0 Synology|28 C6 8E QNAP|24 5E BE QNAP|00 08 9B QNAP|E8 48 B8 QNAP|40 8D 5C QNAP|00 1D 60 QNAP|00 0C 29 QNAP|8C 16 45 QNAP|CC 8E AD QNAP|00 14 FD Thecus|00 90 A9 Western Digital|00 14 EE Western Digital|00 1F E1 Western Digital|00 1B 2F Western Digital|00 E0 4C Western Digital|00 24 2B Western Digital|B0 3A 8C Western Digital|00 1E 6B Western Digital|B8 27 EB Western Digital|54 F8 F0 Western Digital|00 26 40 Buffalo|10 6F 3F Buffalo|34 76 C5 Buffalo|00 0D 0B Buffalo|00 16 01 Buffalo|00 1D 73 Buffalo|00 24 A5 Buffalo|4C E6 76 Buffalo|84 AF EC Buffalo|CC E1 D5 Buffalo|DC FB 02 Buffalo
# Kameras
44 19 B6 Hikvision|54 C4 15 Hikvision|58 03 FB Hikvision|8C E7 48 Hikvision|A4 14 37 Hikvision|BC AD 28 Hikvision|C0 56 E3 Hikvision|C4 2F 90 Hikvision|28 57 BE Hikvision|4C BD 8F Hikvision|D4 E8 53 Hikvision|E0 50 8B Hikvision|E8 A0 ED Hikvision|00 40 48 Hikvision|18 68 CB Hikvision|2C A5 9C Hikvision|3C 1B F8 Hikvision|40 AC BF Hikvision|78 10 9A Hikvision|98 DF 82 Hikvision|AC CB 51 Hikvision|B4 A3 82 Hikvision|C8 02 8F Hikvision|E4 1A F2 Hikvision|F8 4D FC Hikvision
3C EF 8C Dahua|4C 11 BF Dahua|9C 8E CD Dahua|A0 BD 1D Dahua|B4 4C 3B Dahua|E0 50 8B Dahua|F0 A0 B1 Dahua|38 AF 29 Dahua|8C E7 48 Dahua|3C 15 FB Dahua|5C F3 70 Dahua|74 3C 30 Dahua|90 02 A9 Dahua|BC 32 5F Dahua|FC 5F 49 Dahua|28 E3 47 Dahua|D4 43 0E Dahua|E4 24 6C Dahua|7C 14 46 Dahua
EC 71 DB Reolink|2C 6F F7 Reolink|AC C8 A9 Reolink|00 62 6E Reolink|0C 4A 00 Reolink|9C 8E CD Reolink|B4 7D C7 Reolink
00 40 8C Axis|AC CC 8E Axis|B8 A4 4F Axis|E8 27 25 Axis
7C DD 90 Shenzhen Ogemray (IP-Kamera)|00 12 FB Foscam|E0 B9 4D Foscam|C0 F6 C2 Foscam|00 62 6E Foscam|30 A4 33 Foscam|A4 D5 C2 Ring (Amazon)|34 3E A4 Ring (Amazon)|30 D5 00 Ring (Amazon)|8C 60 E7 Ring (Amazon)|3C 22 FB Ring (Amazon)|3C 5F 0A Ring (Amazon)|E0 DB D1 Ring (Amazon)|18 B4 30 Nest (Google)|64 16 66 Nest (Google)|D8 EB 46 Nest (Google)|60 05 5A Nest (Google)|00 17 88 Signify (Hue)|2C 9A 4E TP-Link Tapo|5C E9 31 TP-Link Tapo|6C 5A B0 TP-Link Tapo|B0 95 75 TP-Link Tapo|C0 C9 E3 TP-Link Tapo|30 DE 4B TP-Link Tapo|A8 42 A1 TP-Link Tapo|3C 52 A1 TP-Link Tapo|10 27 F5 TP-Link Tapo|48 22 54 TP-Link Tapo|5C A6 E6 TP-Link Tapo|78 8C B5 TP-Link Tapo|9C 53 22 TP-Link Tapo|D8 47 32 TP-Link Tapo|E8 48 B8 TP-Link Tapo|28 87 BA TP-Link Tapo|CC 68 B6 TP-Link Tapo|40 ED 00 TP-Link Tapo|14 EB B6 TP-Link Tapo|1C 61 B4 TP-Link Tapo|24 2F D0 TP-Link Tapo|34 60 F9 TP-Link Tapo
# Fernseher / Konsolen / Streaming
00 09 DF LG|00 1C 62 LG|00 1E 75 LG|00 1F 6B LG|00 1F E3 LG|00 21 FB LG|00 22 A9 LG|00 24 83 LG|00 25 E5 LG|00 26 E2 LG|00 34 DA LG|00 AA 70 LG|00 E0 91 LG|10 68 3F LG|10 F1 F2 LG|14 C9 13 LG|20 21 A5 LG|2C 54 CF LG|2C 59 8A LG|30 76 6F LG|34 4D F7 LG|34 FC EF LG|38 8C 50 LG|3C BD D8 LG|40 B0 FA LG|48 59 29 LG|50 55 27 LG|58 3F 54 LG|58 A2 B5 LG|60 E3 AC LG|64 89 9A LG|64 99 5D LG|64 BC 0C LG|6C D6 8A LG|70 05 14 LG|74 A7 22 LG|78 F8 82 LG|88 36 6C LG|88 C9 D0 LG|8C 3A E3 LG|98 93 CC LG|98 D6 F7 LG|A0 39 F7 LG|A8 16 B2 LG|A8 92 2C LG|AC 0D 1B LG|B4 0E DC LG|B4 E6 2A LG|B8 1D AA LG|BC 8C CD LG|BC F5 AC LG|C4 36 55 LG|C4 9A 02 LG|C8 02 8F LG|C8 08 E9 LG|CC 2D 8C LG|CC FA 00 LG|D0 13 FD LG|E8 5B 5B LG|E8 F2 E2 LG|F0 1C 13 LG|F8 0C F3 LG|F8 95 C7 LG|F8 A9 D0 LG|FC 7D 61 LG
00 01 4A Sony|00 13 A9 Sony|00 19 C5 Sony|00 1A 80 Sony|00 1D BA Sony|00 24 BE Sony|00 D9 D1 Sony PlayStation|00 E4 21 Sony|04 5D 4B Sony|0C FE 45 Sony PlayStation|10 4F A8 Sony|18 AF 61 Sony|1C 7B 21 Sony|28 0D FC Sony PlayStation|30 F9 ED Sony|3C 07 71 Sony|40 B8 37 Sony|54 42 49 Sony|58 17 0C Sony|70 9E 29 Sony PlayStation|78 84 3C Sony|78 C8 81 Sony PlayStation|84 00 D2 Sony|8C B8 4A Sony|A8 E3 EE Sony|AC 89 95 Sony|B0 05 94 Sony|BC 60 A7 Sony PlayStation|C8 63 F1 Sony PlayStation|D4 4B 5E Sony|E0 B9 BA Sony|F0 BF 97 Sony|F8 46 1C Sony PlayStation|FC 0F E6 Sony PlayStation|FC F1 52 Sony|00 04 1F Sony PlayStation|00 15 C1 Sony PlayStation|00 19 C5 Sony PlayStation|00 1F A7 Sony PlayStation|00 24 8D Sony PlayStation|00 D9 D1 Sony PlayStation|1C 98 C1 Sony PlayStation|B0 52 16 Sony PlayStation|2C CC 44 Sony PlayStation|40 49 0F Sony PlayStation|F8 D0 AC Sony PlayStation
00 09 BF Nintendo|00 16 56 Nintendo|00 17 AB Nintendo|00 19 1D Nintendo|00 19 FD Nintendo|00 1A E9 Nintendo|00 1B 7A Nintendo|00 1B EA Nintendo|00 1C BE Nintendo|00 1D BC Nintendo|00 1E 35 Nintendo|00 1E A9 Nintendo|00 1F 32 Nintendo|00 1F C5 Nintendo|00 21 47 Nintendo|00 21 BD Nintendo|00 22 4C Nintendo|00 22 AA Nintendo|00 22 D7 Nintendo|00 23 31 Nintendo|00 23 CC Nintendo|00 24 1E Nintendo|00 24 44 Nintendo|00 24 F3 Nintendo|00 25 A0 Nintendo|00 26 59 Nintendo|00 27 09 Nintendo|04 03 D6 Nintendo|18 2A 7B Nintendo|2C 10 C1 Nintendo|34 AF 2C Nintendo|40 D2 8A Nintendo|40 F4 07 Nintendo|58 2F 40 Nintendo|58 BD A3 Nintendo|5C 52 1E Nintendo|64 B5 C6 Nintendo|78 A2 A0 Nintendo|7C BB 8A Nintendo|8C 56 C5 Nintendo|8C CD E8 Nintendo|98 41 5C Nintendo|98 B6 E9 Nintendo|98 E8 FA Nintendo|9C E6 35 Nintendo|A4 38 CC Nintendo|A4 5C 27 Nintendo|A4 C0 E1 Nintendo|B8 78 26 Nintendo|B8 8A EC Nintendo|B8 AE 6E Nintendo|CC 9E 00 Nintendo|CC FB 65 Nintendo|D8 6B F7 Nintendo|DC 68 EB Nintendo|E0 0C 7F Nintendo|E0 E7 51 Nintendo|E8 4E CE Nintendo|EC C4 0D Nintendo|04 03 D6 Nintendo|00 1F 32 Nintendo
B0 A7 37 Roku|D8 31 34 Roku|00 0D 4B Roku|B8 3E 59 Roku|CC 6D A0 Roku|08 05 81 Roku|20 EF BD Roku|DC 3A 5E Roku|C8 3A 6B Roku|D4 E2 2F Roku|84 EA ED Roku|10 59 32 Roku
# Switches / WLAN
00 1F 45 Aerohive|00 03 7F Atheros|D4 CA 6D Routerboard|00 0F E2 Hangzhou H3C|18 4B 0D Ruckus|F0 B5 2B Ruckus|2C 5D 93 Ruckus|00 24 82 Ruckus|8C 0C 90 Ruckus|C4 10 8A Ruckus|D8 38 FC Ruckus|E0 10 7F Ruckus|34 FC B9 Aruba|00 0B 86 Aruba|00 1A 1E Aruba|00 24 6C Aruba|04 BD 88 Aruba|18 64 72 Aruba|20 4C 03 Aruba|24 DE C6 Aruba|40 E3 D6 Aruba|6C F3 7F Aruba|70 3A 0E Aruba|84 D4 7E Aruba|94 B4 0F Aruba|9C 1C 12 Aruba|AC A3 1E Aruba|B4 5D 50 Aruba|D8 C7 C8 Aruba|F0 5C 19 Aruba|00 04 96 Extreme|00 01 30 Extreme|00 E0 2B Extreme|B4 C7 99 Extreme|D8 84 66 Extreme|00 1B 2B Cisco|00 1C F6 Cisco|00 23 04 Cisco|00 26 0B Cisco|00 1E 7A Cisco|CC EF 48 Cisco|E4 AA 5D Cisco|F4 CF E2 Cisco|00 1A 6C Cisco|00 1B 54 Cisco|00 21 1B Cisco|00 23 5E Cisco|E8 B7 48 Cisco|00 1D 45 Cisco|00 24 97 Cisco|00 26 99 Cisco|00 0F 23 Cisco|00 11 21 Cisco|70 CA 9B Cisco|B4 14 89 Cisco|28 94 0F Cisco|1C E8 5D Cisco|D0 C2 82 Cisco|E8 65 49 Cisco|A0 EC F9 Cisco|00 1E 14 Cisco|C8 9C 1D Cisco|6C 41 6A Cisco|7C AD 74 Cisco|58 97 1E Cisco|00 3A 9A Cisco|00 3A 99 Cisco|00 23 EB Cisco|E0 5F B9 Cisco|00 26 CB Cisco|B0 FA EB Cisco|D4 8C B5 Cisco|00 1B D5 Cisco|F8 66 F2 Cisco|50 06 04 Cisco|70 10 5C Cisco|78 BC 1A Cisco|88 90 8D Cisco|7C 69 F6 Cisco|00 15 FA Cisco|E0 2F 6D Cisco|00 0B BE Cisco|00 18 73 Cisco|4C 4E 35 Cisco|00 1F 9E Cisco|00 25 45 Cisco|00 0D 65 Cisco|E8 04 62 Cisco|00 19 55 Cisco|C0 62 6B Cisco|BC 16 65 Cisco|00 17 E0 Cisco|C4 71 FE Cisco|F4 4E 05 Cisco|00 1C 58 Cisco|00 26 51 Cisco|B8 BE BF Cisco|00 1E BD Cisco|00 1F 6C Cisco|6C 50 4D Cisco|A8 B1 D4 Cisco|84 B8 02 Cisco|3C 0E 23 Cisco|00 1A 30 Cisco|00 1C 0E Cisco|00 22 90 Cisco|F0 29 29 Cisco|F0 F7 55 Cisco|00 1B 0C Cisco|A4 56 30 Cisco|00 1F CA Cisco|F0 7F 06 Cisco|00 1B 8F Cisco|00 22 BD Cisco|00 23 5D Cisco|00 24 F7 Cisco|00 26 98 Cisco|04 FE 7F Cisco|1C AA 07 Cisco|30 F7 0D Cisco|40 55 39 Cisco|54 78 1A Cisco|58 8D 09 Cisco|64 00 F1 Cisco|68 BD AB Cisco|6C 20 56 Cisco|74 A2 E6 Cisco|8C B6 4F Cisco|A4 0C C3 Cisco|A8 0C 0D Cisco|AC F2 C5 Cisco|B0 AA 77 Cisco|C0 67 AF Cisco|CC D8 C1 Cisco|D0 D0 FD Cisco|E0 2F 6D Cisco|F0 25 72 Cisco|F8 72 EA Cisco|FC 99 47 Cisco
# Weitere
00 50 C2 IEEE Registration Authority|70 B3 D5 IEEE Registration Authority|00 1B C5 IEEE Registration Authority|40 D8 55 IEEE Registration Authority|04 3D 98 Chongqing Fugui|00 1E 4C Hon Hai (Foxconn)|00 22 69 Hon Hai (Foxconn)|00 26 5E Hon Hai (Foxconn)|60 D8 19 Hon Hai (Foxconn)|7C 7A 91 Intel|00 24 2C Hon Hai (Foxconn)|00 1C 26 Hon Hai (Foxconn)|00 19 7E Hon Hai (Foxconn)|00 1F E2 Hon Hai (Foxconn)|00 21 00 Gemtek|00 1D 60 ASUS|00 1E 8C ASUS|00 23 54 ASUS|00 24 8C ASUS|00 26 18 ASUS|00 E0 18 ASUS|20 CF 30 ASUS|38 D5 47 ASUS|48 5B 39 ASUS|60 45 CB ASUS|74 D0 2B ASUS|90 E6 BA ASUS|AC 9E 17 ASUS|BC AE C5 ASUS|E0 3F 49 ASUS|F4 6D 04 ASUS|00 1A 92 ASUS|00 1B FC ASUS|00 1D 60 ASUS|00 1E 8C ASUS|00 22 15 ASUS|00 23 54 ASUS|00 24 8C ASUS|00 26 18 ASUS|00 E0 18 ASUS|08 60 6E ASUS|10 7B 44 ASUS|10 BF 48 ASUS|10 C3 7B ASUS|14 DA E9 ASUS|14 DD A9 ASUS|1C 87 2C ASUS|1C B7 2C ASUS|20 CF 30 ASUS|2C 4D 54 ASUS|2C 56 DC ASUS|2C FD A1 ASUS|30 5A 3A ASUS|30 85 A9 ASUS|34 97 F6 ASUS|38 2C 4A ASUS|38 D5 47 ASUS|3C 7C 3F ASUS|40 16 7E ASUS|40 B0 76 ASUS|48 5B 39 ASUS|4C ED FB ASUS|50 46 5D ASUS|50 EB F6 ASUS|54 04 A6 ASUS|60 45 CB ASUS|60 A4 4C ASUS|70 4D 7B ASUS|70 8B CD ASUS|74 D0 2B ASUS|78 24 AF ASUS|88 D7 F6 ASUS|90 E6 BA ASUS|9C 5C 8E ASUS|A0 36 BC ASUS|A8 5E 45 ASUS|AC 22 0B ASUS|AC 9E 17 ASUS|B0 6E BF ASUS|BC AE C5 ASUS|BC EE 7B ASUS|C8 60 00 ASUS|C8 7F 54 ASUS|D0 17 C2 ASUS|D4 5D 64 ASUS|D8 50 E6 ASUS|E0 3F 49 ASUS|E0 D5 5E ASUS|F0 2F 74 ASUS|F0 79 59 ASUS|F4 6D 04 ASUS|F8 32 E4 ASUS|FC 34 97 ASUS|FC C2 33 ASUS|04 92 26 ASUS|08 BF B8 ASUS|24 4B FE ASUS|7C 10 C9 ASUS|00 1F 16 Wistron|00 26 2D Wistron|F0 76 1C Compal|00 16 D4 Compal|00 1D 72 Wistron|00 90 F5 Clevo|00 1A 73 Gemtek|00 1B 24 Quanta|00 23 8B Quanta|00 26 9E Quanta|C8 0A A9 Quanta|00 1E 68 Quanta|00 1E 4C Hon Hai|00 E0 4C Realtek|00 1C BF Intel|00 21 5C Intel|00 21 6A Intel|00 22 FA Intel|00 23 14 Intel|00 23 15 Intel|00 24 D7 Intel|00 27 10 Intel|10 0B A9 Intel|24 77 03 Intel|34 02 86 Intel|34 13 E8 Intel|3C A9 F4 Intel|40 25 C2 Intel|48 51 B7 Intel|4C 34 88 Intel|4C 79 BA Intel|5C 87 9C Intel|60 36 DD Intel|60 57 18 Intel|60 67 20 Intel|60 6C 66 Intel|64 80 99 Intel|68 05 CA Intel|68 17 29 Intel|6C 29 95 Intel|6C 88 14 Intel|7C 5C F8 Intel|7C 7A 91 Intel|80 00 0B Intel|80 86 F2 Intel|84 3A 4B Intel|88 53 2E Intel|8C A9 82 Intel|90 2E 1C Intel|94 65 9C Intel|98 4F EE Intel|9C 4E 36 Intel|A0 88 69 Intel|A0 88 B4 Intel|A4 02 B9 Intel|A4 34 D9 Intel|AC 2B 6E Intel|AC 72 89 Intel|AC 7B A1 Intel|AC ED 5C Intel|B4 6B FC Intel|B4 6D 83 Intel|B8 08 CF Intel|B8 8A 60 Intel|BC 77 37 Intel|C4 85 08 Intel|C4 D9 87 Intel|C8 F7 50 Intel|CC 2F 71 Intel|D0 57 7B Intel|D8 F2 CA Intel|DC 53 60 Intel|DC A2 66 Intel|E0 94 67 Intel|E4 02 9B Intel|E4 B3 18 Intel|E8 B1 FC Intel|F4 06 69 Intel|F4 8C 50 Intel|F8 16 54 Intel|F8 59 71 Intel|FC F8 AE Intel|00 25 00 Apple|E4 CE 8F Apple
"""


def _build() -> None:
    for line in _RAW.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for entry in line.split("|"):
            entry = entry.strip()
            if not entry:
                continue
            m = re.match(r"^([0-9A-Fa-f]{2}\s?[0-9A-Fa-f]{2}\s?[0-9A-Fa-f]{2})\s+(.+)$", entry)
            if not m:
                continue
            prefix = m.group(1).replace(" ", "").upper()
            _BUILTIN.setdefault(prefix, m.group(2).strip())


_build()
_EXTERNAL: dict[str, str] = {}
_LOADED_EXTERNAL = False


def _candidate_files() -> list[Path]:
    paths: list[Path] = []
    here = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    for base in (here, Path.cwd()):
        for name in ("oui.txt", "manuf", "manuf.txt"):
            paths.append(base / name)
    env = os.environ.get("NETGUARD_DATA")
    if env:
        for name in ("oui.txt", "manuf", "manuf.txt"):
            paths.append(Path(env) / name)
    try:
        from .storage import data_dir
        for name in ("oui.txt", "manuf", "manuf.txt"):
            paths.append(data_dir() / name)
    except Exception:
        pass
    return paths


def load_external() -> int:
    """Liest eine externe OUI-Liste ein, falls vorhanden. Gibt die Zahl der Einträge zurück."""
    global _LOADED_EXTERNAL
    if _LOADED_EXTERNAL:
        return len(_EXTERNAL)
    _LOADED_EXTERNAL = True
    for p in _candidate_files():
        if not p.is_file():
            continue
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # IEEE: "00-1C-4A   (hex)		AVM GmbH"
                    m = re.match(r"^([0-9A-F]{2})-([0-9A-F]{2})-([0-9A-F]{2})\s+\(hex\)\s+(.+)$", line, re.I)
                    if m:
                        _EXTERNAL["".join(m.group(1, 2, 3)).upper()] = m.group(4).strip()
                        continue
                    # Wireshark manuf: "00:1C:4A\tAVM\tAVM GmbH"
                    m = re.match(r"^([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2})\t([^\t]+)(?:\t(.+))?$", line, re.I)
                    if m:
                        _EXTERNAL["".join(m.group(1, 2, 3)).upper()] = (m.group(5) or m.group(4)).strip()
        except OSError:
            continue
    return len(_EXTERNAL)


def normalize_mac(mac: str) -> str:
    hexs = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(hexs) != 12:
        return (mac or "").strip().lower()
    return ":".join(hexs[i:i + 2] for i in range(0, 12, 2)).lower()


def is_locally_administered(mac: str) -> bool:
    """Zufällige/private MAC (z.B. Smartphones mit Privatadresse)."""
    hexs = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(hexs) < 2:
        return False
    try:
        return bool(int(hexs[:2], 16) & 0x02)
    except ValueError:
        return False


def lookup(mac: str) -> str:
    hexs = re.sub(r"[^0-9A-Fa-f]", "", mac or "").upper()
    if len(hexs) < 6:
        return ""
    prefix = hexs[:6]
    load_external()
    v = _EXTERNAL.get(prefix) or _BUILTIN.get(prefix)
    if v:
        return v
    if is_locally_administered(mac):
        return "(private/zufällige MAC)"
    return ""
