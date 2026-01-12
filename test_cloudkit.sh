#!/bin/bash
# CloudKit 测试和调试脚本

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_FILE="$HOME/Library/Group Containers/group.com.encnotes/encnotes.log"

echo "=================================="
echo "CloudKit 测试和调试工具"
echo "=================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 函数：打印成功消息
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

# 函数：打印错误消息
print_error() {
    echo -e "${RED}✗${NC} $1"
}

# 函数：打印警告消息
print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 函数：检查 CloudKit 框架
check_cloudkit_framework() {
    echo "1. 检查 CloudKit 框架..."
    if python3 -c "from CloudKit import CKContainer; print('OK')" 2>/dev/null | grep -q "OK"; then
        print_success "CloudKit 框架已安装"
        return 0
    else
        print_error "CloudKit 框架未安装"
        echo "   请运行: pip3 install pyobjc-framework-CloudKit"
        return 1
    fi
}

# 函数：检查 iCloud 登录状态
check_icloud_status() {
    echo ""
    echo "2. 检查 iCloud 登录状态..."
    if defaults read MobileMeAccounts Accounts &>/dev/null; then
        print_success "已登录 iCloud 账户"
        return 0
    else
        print_warning "未登录 iCloud 账户"
        echo "   请在系统设置中登录 iCloud"
        return 1
    fi
}

# 函数：测试 CloudKit 初始化
test_cloudkit_init() {
    echo ""
    echo "3. 测试 CloudKit 初始化..."
    cd "$SCRIPT_DIR"
    if python3 test_cloudkit_init.py 2>&1 | grep -q "测试完成"; then
        print_success "CloudKit 初始化测试通过"
        return 0
    else
        print_error "CloudKit 初始化测试失败"
        echo "   运行 'python3 test_cloudkit_init.py' 查看详细信息"
        return 1
    fi
}

# 函数：显示最近的日志
show_recent_logs() {
    echo ""
    echo "4. 最近的日志（最后 20 行）..."
    if [ -f "$LOG_FILE" ]; then
        echo "-----------------------------------"
        tail -20 "$LOG_FILE"
        echo "-----------------------------------"
    else
        print_warning "日志文件不存在: $LOG_FILE"
    fi
}

# 函数：启动应用并监控日志
start_app_with_logs() {
    echo ""
    echo "5. 启动应用并监控日志..."
    echo "   按 Ctrl+C 停止"
    echo ""
    
    # 在后台启动应用
    cd "$SCRIPT_DIR"
    python3 main.py &
    APP_PID=$!
    
    # 等待日志文件创建
    sleep 2
    
    # 监控日志
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE" | grep --line-buffered -i "cloudkit\|sync\|error\|fail"
    else
        print_error "日志文件未创建"
    fi
    
    # 清理
    kill $APP_PID 2>/dev/null || true
}

# 函数：清理 CloudKit 数据
clean_cloudkit_data() {
    echo ""
    echo "清理 CloudKit 数据..."
    
    CLOUDKIT_DIR="$HOME/Library/Group Containers/group.com.encnotes/CloudKit"
    SYNC_CONFIG="$HOME/Library/Group Containers/group.com.encnotes/sync_config.json"
    
    if [ -d "$CLOUDKIT_DIR" ]; then
        rm -rf "$CLOUDKIT_DIR"
        print_success "已删除 CloudKit 缓存目录"
    fi
    
    if [ -f "$SYNC_CONFIG" ]; then
        rm "$SYNC_CONFIG"
        print_success "已删除同步配置文件"
    fi
    
    echo ""
    print_success "清理完成"
}

# 函数：显示帮助信息
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  check     - 检查 CloudKit 环境"
    echo "  test      - 运行 CloudKit 初始化测试"
    echo "  run       - 启动应用并监控日志"
    echo "  logs      - 显示最近的日志"
    echo "  clean     - 清理 CloudKit 数据"
    echo "  help      - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 check   # 检查环境"
    echo "  $0 test    # 运行测试"
    echo "  $0 run     # 启动应用"
}

# 主函数
main() {
    case "${1:-check}" in
        check)
            check_cloudkit_framework
            check_icloud_status
            echo ""
            echo "=================================="
            echo "环境检查完成"
            echo "=================================="
            ;;
        test)
            check_cloudkit_framework || exit 1
            test_cloudkit_init
            ;;
        run)
            check_cloudkit_framework || exit 1
            start_app_with_logs
            ;;
        logs)
            show_recent_logs
            ;;
        clean)
            clean_cloudkit_data
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知选项: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
