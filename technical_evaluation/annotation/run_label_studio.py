"""启动 Label Studio，并加载 annotation/raw_data 下的结构化 JSON 数据。"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, parse, request


LABEL_CONFIG = """
<View>
    <Header value="Step 级人工标注"/>
    <Text name="source_file_text" value="来源文件：$source_file"/>
    <Text name="data_id_text" value="数据ID：$data_id"/>
    <Text name="step_id_text" value="Step ID：$step_id"/>
    <Text name="task_text" value="$task"/>
    <Text name="step_text" value="$step_text"/>
    <Choices name="step_label" toName="step_text" choice="single" showInline="true" required="true">
        <Choice value="正确"/>
        <Choice value="部分正确"/>
        <Choice value="错误"/>
  </Choices>
    <TextArea name="step_comment" toName="step_text" placeholder="对该 step 的备注"/>
</View>
""".strip()


def ensure_label_studio_installed() -> None:
    try:
        import label_studio  # noqa: F401
    except ImportError:
        print("未检测到 label-studio，正在尝试安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "label-studio"])


def format_single_step_text(step: dict[str, Any]) -> str:
    step_id = step.get("step_id", "")
    target_objective = step.get("TARGET OBJECTIVE", "")
    evaluation = step.get("EVALUATION", "")
    action = step.get("ACTION", "")
    ai_reasoning = step.get("AI REASONING", "")
    memory = step.get("MEMORY", "")
    lines = [
        f"Step {step_id}",
        f"TARGET OBJECTIVE: {target_objective}",
        f"EVALUATION: {evaluation}",
        f"ACTION: {action}",
        f"AI REASONING: {ai_reasoning}",
        f"MEMORY: {memory}",
    ]
    return "\n".join(lines)


def convert_raw_json_to_tasks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    steps = raw.get("steps", [])
    if not isinstance(steps, list):
        return []

    task_list: list[dict[str, Any]] = []
    for step in steps:
        step_id = step.get("step_id", "")
        task_data = {
            "data_id": raw.get("data_id", ""),
            "source_file": raw.get("source_file", ""),
            "task": raw.get("task", ""),
            "persona": raw.get("persona", ""),
            "launch": raw.get("launch", ""),
            "starting_task_prompt": raw.get("starting_task_prompt", ""),
            "step_id": step_id,
            "step_text": format_single_step_text(step),
        }
        task_list.append({"data": task_data})
    return task_list


def load_raw_tasks(raw_data_dir: Path) -> list[dict[str, Any]]:
    if not raw_data_dir.exists() or not raw_data_dir.is_dir():
        raise FileNotFoundError(f"raw_data 目录不存在: {raw_data_dir}")

    tasks: list[dict[str, Any]] = []
    json_files = sorted(raw_data_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"raw_data 目录下未找到 JSON 文件: {raw_data_dir}")

    for file_path in json_files:
        with file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        tasks.extend(convert_raw_json_to_tasks(raw))
    return tasks


def dump_tasks(tasks: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(tasks, file, ensure_ascii=False, indent=2)


def wait_for_port(url: str, timeout_seconds: int = 60) -> bool:
    parsed = parse.urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(1)
    return False


def api_request(method: str, url: str, api_key: str, payload: Any | None = None) -> Any | None:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url=url, data=data, method=method)
    req.add_header("Authorization", f"Token {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8").strip()
            return json.loads(content) if content else None
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"API 请求失败: {method} {url} -> {exc.code}\n{body}")
    except error.URLError as exc:
        print(f"无法访问 Label Studio API: {exc}")
    return None


def get_or_create_project(base_url: str, api_key: str, project_title: str) -> int | None:
    projects_resp = api_request("GET", f"{base_url}/api/projects?page_size=100", api_key)
    if projects_resp and isinstance(projects_resp, dict):
        for project in projects_resp.get("results", []):
            if project.get("title") == project_title:
                project_id = project.get("id")
                if isinstance(project_id, int):
                    print(f"复用已有项目: {project_title} (id={project_id})")
                    return project_id

    created = api_request(
        "POST",
        f"{base_url}/api/projects",
        api_key,
        payload={"title": project_title, "label_config": LABEL_CONFIG},
    )
    if created and isinstance(created, dict) and isinstance(created.get("id"), int):
        project_id = created["id"]
        print(f"已创建项目: {project_title} (id={project_id})")
        return project_id
    return None


def import_tasks(base_url: str, api_key: str, project_id: int, tasks: list[dict[str, Any]]) -> bool:
    imported = api_request(
        "POST",
        f"{base_url}/api/projects/{project_id}/import",
        api_key,
        payload=tasks,
    )
    if imported is None:
        return False
    print("已通过 API 导入任务到 Label Studio。")
    return True


def start_label_studio(annotation_dir: Path) -> subprocess.Popen[Any]:
    cmd = [
        sys.executable,
        "-m",
        "label_studio",
        "start",
        "--init",
        "--project",
        str(annotation_dir),
    ]
    print(f"正在启动 Label Studio，工作目录: {annotation_dir}")
    return subprocess.Popen(cmd)


def parse_args() -> argparse.Namespace:
    annotation_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="启动 Label Studio 并加载 raw_data 结构化 JSON")
    parser.add_argument("--raw-dir", default=str(annotation_dir / "raw_data"), help="raw_data 目录")
    parser.add_argument(
        "--tasks-output",
        default=str(annotation_dir / "label_studio_tasks.json"),
        help="导出的 Label Studio 任务文件路径",
    )
    parser.add_argument("--url", default="http://localhost:8080", help="Label Studio URL")
    parser.add_argument(
        "--project-title",
        default="EvalAgent RawData Annotation",
        help="自动导入时使用的项目名称",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LABEL_STUDIO_API_KEY", ""),
        help="Label Studio API Key（可通过环境变量 LABEL_STUDIO_API_KEY 提供）",
    )
    parser.add_argument("--prepare-only", action="store_true", help="仅转换并导出任务文件，不启动 Label Studio")
    parser.add_argument("--skip-import", action="store_true", help="仅启动并导出任务文件，不调用 API 自动导入")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    annotation_dir = Path(__file__).resolve().parent
    raw_dir = Path(args.raw_dir).resolve()
    tasks_output = Path(args.tasks_output).resolve()

    ensure_label_studio_installed()

    tasks = load_raw_tasks(raw_dir)
    dump_tasks(tasks, tasks_output)
    print(f"已生成任务文件: {tasks_output}")
    print(f"共转换 {len(tasks)} 条 step 级任务。")

    if args.prepare_only:
        print("已完成任务文件准备（prepare-only），未启动 Label Studio。")
        return

    process = start_label_studio(annotation_dir)
    print(f"Label Studio 启动地址: {args.url}")

    if args.skip_import:
        print("已跳过自动导入。可在 Label Studio 页面手动导入上述任务文件。")
    elif not args.api_key:
        print("未提供 API Key，跳过自动导入。")
        print("可设置环境变量 LABEL_STUDIO_API_KEY 后重跑，或手动导入任务文件。")
    elif not wait_for_port(args.url, timeout_seconds=60):
        print("Label Studio 端口未在预期时间内就绪，自动导入跳过。")
    else:
        project_id = get_or_create_project(args.url, args.api_key, args.project_title)
        if project_id is None or not import_tasks(args.url, args.api_key, project_id, tasks):
            print("自动导入失败，请在 Label Studio 页面手动导入任务文件。")

    try:
        process.wait()
    except KeyboardInterrupt:
        print("收到中断信号，正在关闭 Label Studio...")
        process.terminate()


if __name__ == "__main__":
    main()
