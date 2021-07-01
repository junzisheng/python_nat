# python_nat
![](https://img.shields.io/badge/Python-3.7+-brightgreen.svg)

使用python asyncio开发的内网穿透工具

# 运行server

`python3 server.py `
在公网服务器启动服务端
```
[root@ia1k2jkl2 python_nat]# python3 main.py
INFO:     Started server process [32418]
INFO:     Waiting for application startup.
2021-07-01 11:29:21.355 | INFO     | server.relay_server:start:97 - RelayServer serving on 0.0.0.0:81
2021-07-01 11:29:21.355 | INFO     | server.manager_server:start:91 - ManagerServer serving on 0.0.0.0:82
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:9001 (Press CTRL+C to quit)
```
添加映射规则 将3389暴露到远程服务器的8899端口
```
[root@ia1k2jkl2 python_nat]# cd command/
[root@ia1k2jkl2 command]# python3 helper.py --help
Usage: helper.py [OPTIONS] COMMAND [ARGS]...

  python nat command line

Options:
  --help  Show this message and exit.

Commands:
  add    add nat mapping with endpoint e.g: add 127.0.0.1:8888
  ls     list nat mapping
  rm     rm nat mapping with log id e.g: rm 1
  watch
[root@ia1k2jkl2 command]# 


[root@ia1k2jkl2 command]# python3 helper.py  add 127.0.0.1:3389 --bind-port 8899
"success: 127.0.0.1:3389 --> 0.0.0.0:8899 created"
[root@ia1k2jkl2 command]# 

```
内网修改settings.Setting.remote_host 为公网服务器ip
启动客户端
```
pyhon3 client.py
```

访问 {remote_host}:8899 即可远程控制内网机器
