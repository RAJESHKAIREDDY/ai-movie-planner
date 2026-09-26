#!/bin/bash
# Quick test commands for AI Movie Planner
# Make executable: chmod +x .test_commands.sh
# Usage: source .test_commands.sh (to load aliases)

# Navigate to test directory
cd "$(dirname "$0")"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== AI Movie Planner Test Commands ===${NC}"

# 1. Run all tests
alias test-all='echo -e "${YELLOW}Running all tests...${NC}" && pytest test_frontend.py -v'

# 2. Run MISSING_MOVIE bug test specifically
alias test-bug='echo -e "${YELLOW}Testing MISSING_MOVIE bug prevention...${NC}" && pytest test_frontend.py::TestMovieIdResolution::test_save_recommendation_rejects_missing_movie -v'

# 3. Run multi-word group name tests
alias test-groups='echo -e "${YELLOW}Testing multi-word group names...${NC}" && pytest test_frontend.py::TestGroupNameHandling -v'

# 4. Run with coverage
alias test-coverage='echo -e "${YELLOW}Running tests with coverage report...${NC}" && pytest test_frontend.py --cov=frontend --cov=movie_mcp_server --cov-report=html --cov-report=term && echo -e "${GREEN}Coverage report: htmlcov/index.html${NC}"'

# 5. Run only unit tests (fast)
alias test-unit='echo -e "${YELLOW}Running unit tests only...${NC}" && pytest test_frontend.py -v -m unit'

# 6. Run regression tests
alias test-regressions='echo -e "${YELLOW}Running regression tests...${NC}" && pytest test_frontend.py::TestRegressions -v'

# 7. Run and show print statements (debugging)
alias test-debug='echo -e "${YELLOW}Running tests with debug output...${NC}" && pytest test_frontend.py -v -s'

# 8. Quick smoke test (most critical tests only)
alias test-quick='echo -e "${YELLOW}Running quick smoke test...${NC}" && pytest test_frontend.py::TestMovieIdResolution -v && pytest test_frontend.py::TestGroupNameHandling::test_uuid_pattern_validation -v'

# 9. Install test dependencies
alias test-setup='echo -e "${YELLOW}Installing test dependencies...${NC}" && pip install pytest pytest-mock responses pytest-cov && echo -e "${GREEN}Setup complete!${NC}"'

# 10. Watch mode (re-run tests on file changes) - requires pytest-watch
alias test-watch='echo -e "${YELLOW}Watching for file changes...${NC}" && ptw test_frontend.py -- -v'

echo -e ""
echo -e "${GREEN}Available commands:${NC}"
echo -e "  ${YELLOW}test-all${NC}          - Run all tests"
echo -e "  ${YELLOW}test-bug${NC}          - Test MISSING_MOVIE bug fix"
echo -e "  ${YELLOW}test-groups${NC}       - Test multi-word group names"
echo -e "  ${YELLOW}test-coverage${NC}     - Run with coverage report"
echo -e "  ${YELLOW}test-unit${NC}         - Run only unit tests (fast)"
echo -e "  ${YELLOW}test-regressions${NC}  - Run regression tests"
echo -e "  ${YELLOW}test-debug${NC}        - Run with print statements"
echo -e "  ${YELLOW}test-quick${NC}        - Quick smoke test"
echo -e "  ${YELLOW}test-setup${NC}        - Install dependencies"
echo -e "  ${YELLOW}test-watch${NC}        - Watch mode (requires pytest-watch)"
echo -e ""
echo -e "${GREEN}Example usage:${NC}"
echo -e "  $ test-all"
echo -e "  $ test-bug"
echo -e ""

# Direct execution mode (if script is run, not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo -e "${YELLOW}Running all tests...${NC}"
    pytest test_frontend.py -v
fi
