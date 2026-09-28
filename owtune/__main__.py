import sys


def main() -> None:
    # 화면 복구 감시 프로세스: Qt 없이 가볍게 실행
    if len(sys.argv) >= 3 and sys.argv[1] == "--guard":
        from .display_service import run_guard

        run_guard(sys.argv[2])
        return
    from .ui.app import run

    sys.exit(run())


if __name__ == "__main__":
    main()
