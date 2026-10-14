"""
猫砂盆监控命令行工具

全局命令 catmon，替代原 MCP HTTP 服务的五个工具接口。
业务逻辑直接复用 LitterMonitorMCPServer，日志走 stderr，stdout 只输出 JSON。

用法：
    catmon unidentified                              列出未识别照片
    catmon stats [DATE]                              每日统计（默认今天）
    catmon records [--start DATE] [--end DATE] [--cat NAME] [--limit N]
    catmon add --records JSON|-|@FILE                批量添加使用记录
    catmon mark PATH [PATH ...]                      标记无法识别
    catmon status                                    检查监控系统运行状态
"""

import sys
import os
import json
import socket
import logging
import argparse
import subprocess
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
# 主脚本方式运行时 sys.path[0] 是本文件所在目录（src/），其下的 src/mcp 包
# 会遮蔽 fastmcp 依赖的官方 mcp 包导致循环导入，必须先移除
_src_dir = str(Path(__file__).resolve().parent)
if sys.path and os.path.abspath(sys.path[0]) == _src_dir:
    sys.path.pop(0)
sys.path.insert(0, str(project_root))
os.chdir(project_root)

# 先 import（server 内部会 basicConfig 到 stdout），再强制重定向到 stderr，
# 保证 stdout 只有 CLI 的 JSON 输出
from src.mcp.server import LitterMonitorMCPServer

logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr, force=True)


def _load_records(raw: str):
    if raw == '-':
        return json.load(sys.stdin)
    if raw.startswith('@'):
        with open(raw[1:], encoding='utf-8') as f:
            return json.load(f)
    return json.loads(raw)


# 核心三件套对应的监听端口（与 start.bat 自检一致）：main 5002 / web 5000 / go2rtc 1984
_SERVICE_PORTS = {'go2rtc': 1984, 'main': 5002, 'web': 5000}

# git-bash 等精简环境的 PATH 里没有 System32\wbem，必须用绝对路径调 wmic
_WMIC = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'wbem', 'WMIC.exe')


def _port_listening(port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(('127.0.0.1', port)) == 0


def _monitor_processes():
    """返回命令行含 cat-litter-monitor 的 python/pythonw 进程命令行（反斜杠已归一为 /）。"""
    try:
        out = subprocess.run(
            [_WMIC, 'process', 'where', "name='python.exe' or name='pythonw.exe'",
             'get', 'commandline', '/format:csv'],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        out = ''
    return [ln.replace('\\', '/') for ln in out.splitlines() if 'cat-litter-monitor' in ln]


def _go2rtc_running() -> bool:
    try:
        out = subprocess.run(
            [_WMIC, 'process', 'where', "name='go2rtc.exe'", 'get', 'processid'],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        return False
    return any(ln.strip().isdigit() for ln in out.splitlines())


def get_system_status():
    procs = _monitor_processes()

    def proc_running(suffix):
        return any(suffix in p for p in procs)

    components = {}
    for name, port in _SERVICE_PORTS.items():
        if name == 'go2rtc':
            process_running = _go2rtc_running()
        elif name == 'main':
            process_running = proc_running('src/main.py')
        else:
            process_running = proc_running('src/web/app.py')
        components[name] = {
            'process_running': process_running,
            'port_listening': _port_listening(port),
            'port': port,
        }
    components['manager'] = {'process_running': proc_running('src/manager.py')}

    running = all(components[name]['port_listening'] for name in _SERVICE_PORTS)
    return {'running': running, 'components': components}


def main():
    parser = argparse.ArgumentParser(prog='catmon', description='猫砂盆监控命令行工具')
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('unidentified', help='列出未识别照片')

    p_stats = sub.add_parser('stats', help='每日统计（不传日期默认今天）')
    p_stats.add_argument('date', nargs='?', default=None, help='日期 YYYY-MM-DD')

    p_rec = sub.add_parser('records', help='查询使用记录')
    p_rec.add_argument('--start', default=None, help='开始日期 YYYY-MM-DD')
    p_rec.add_argument('--end', default=None, help='结束日期 YYYY-MM-DD')
    p_rec.add_argument('--cat', dest='cat_name', default=None, help='按猫咪名字过滤')
    p_rec.add_argument('--limit', type=int, default=100, help='返回数量限制，默认 100')

    p_add = sub.add_parser('add', help='批量添加使用记录')
    p_add.add_argument('--records', required=True,
                       help='记录 JSON 数组：内联 JSON、- 读 stdin、@FILE 读文件')

    p_mark = sub.add_parser('mark', help='把无法确认的照片标记为无法识别')
    p_mark.add_argument('paths', nargs='+', help='照片路径（路径中须含 YYYY-MM-DD 日期）')

    sub.add_parser('status', help='检查监控系统运行状态（进程与端口）')

    args = parser.parse_args()

    if args.command == 'status':
        result = get_system_status()
    else:
        server = LitterMonitorMCPServer()
        if args.command == 'unidentified':
            result = server.get_unidentified_photos()
        elif args.command == 'stats':
            result = server.get_daily_statistics(record_date=args.date)
        elif args.command == 'records':
            result = server.get_litter_records(
                start_date=args.start, end_date=args.end,
                cat_name=args.cat_name, limit=args.limit,
            )
        elif args.command == 'add':
            result = server.add_litter_records(records=_load_records(args.records))
        elif args.command == 'mark':
            result = server.mark_unidentifiable(photo_paths=args.paths)
        else:
            parser.error(f'未知命令: {args.command}')

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
