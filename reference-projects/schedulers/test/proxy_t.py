import requests
p='54.255.180.19'
proxy = f"SilverDragon91:Q7mR4tP9bX2k@{p}:3129"
proxy = f"socks5://{proxy}"
proxies = {"http": proxy, "https": proxy}
# proxy = "SilverDragon91:Q7mR4tP9bX2k@47.129.41.243:3128"
# proxy = f"http://{proxy}"
# proxies = {"http": proxy, "https": proxy}


def t1():
    session = requests.Session()
    session.proxies.update(proxies)
    response = session.get("https://httpbin.org/ip")
    print(response.text)


def t2():
    response = requests.get("https://httpbin.org/ip", proxies=proxies)
    print(response.json())


def t3():
    response = requests.get("https://graph.facebook.com/v12.0/me", proxies=proxies)
    print(response.json())


def t4():
    response = requests.get("https://graph.facebook.com/v12.0/me")
    print(response.json())


def t5():
    response = requests.get(
        "https://www.kimi.com/chat/d1hp7576rtp2vim04lng", proxies=proxies
    )
    print(response.text)


if __name__ == "__main__":
    t1()
    t2()
