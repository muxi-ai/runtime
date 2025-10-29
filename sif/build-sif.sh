#!/usr/bin/env bash
#
# MUXI Runtime SIF Builder
# Builds Singularity Image Format (SIF) containers for MUXI formations
#
# Usage:
#   ./build-sif.sh [basic|production] [output-name]
#
# Examples:
#   ./build-sif.sh                      # Build basic runtime
#   ./build-sif.sh basic                # Build basic runtime
#   ./build-sif.sh production           # Build production with services
#   ./build-sif.sh basic my-runtime.sif # Custom output name
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BUILD_TYPE="${1:-basic}"
OUTPUT_NAME="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if Apptainer/Singularity is installed
check_singularity() {
    if command -v apptainer &> /dev/null; then
        SINGULARITY_CMD="apptainer"
        print_success "Found Apptainer: $(apptainer --version)"
        return 0
    elif command -v singularity &> /dev/null; then
        SINGULARITY_CMD="singularity"
        print_success "Found Singularity: $(singularity --version)"
        return 0
    else
        return 1
    fi
}

# Check if Docker is available for alternative build
check_docker() {
    if command -v docker &> /dev/null; then
        print_success "Found Docker: $(docker --version | head -n1)"
        return 0
    else
        return 1
    fi
}

# Build using Apptainer/Singularity
build_with_singularity() {
    local def_file="$1"
    local output_file="$2"
    
    print_info "Building with $SINGULARITY_CMD..."
    
    # Check if sudo is needed (Linux typically requires it)
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        print_warning "Building on Linux requires sudo privileges"
        sudo "$SINGULARITY_CMD" build "$output_file" "$def_file"
    else
        "$SINGULARITY_CMD" build "$output_file" "$def_file"
    fi
}

# Build using Docker (fallback method)
build_with_docker() {
    local def_file="$1"
    local output_file="$2"
    
    print_info "Building with Docker + Singularity container..."
    
    docker run --rm --privileged \
        -v "$SCRIPT_DIR:/work" \
        quay.io/singularity/singularity:latest \
        build "/work/$output_file" "/work/$def_file"
}

# Main build function
build_sif() {
    local build_type="$1"
    local output_name="$2"
    
    # Determine definition file and output name
    local def_file
    local default_output
    
    case "$build_type" in
        basic)
            def_file="muxi-runtime.def"
            default_output="muxi-runtime.sif"
            ;;
        production|prod)
            def_file="muxi-runtime-production.def"
            default_output="muxi-runtime-production.sif"
            build_type="production"
            ;;
        *)
            print_error "Unknown build type: $build_type"
            echo "Valid types: basic, production"
            exit 1
            ;;
    esac
    
    # Use custom output name if provided
    local output_file="${output_name:-$default_output}"
    
    print_header "MUXI Runtime SIF Builder"
    echo ""
    print_info "Build Type: $build_type"
    print_info "Definition File: $def_file"
    print_info "Output File: $output_file"
    echo ""
    
    # Check if definition file exists
    if [[ ! -f "$SCRIPT_DIR/$def_file" ]]; then
        print_error "Definition file not found: $def_file"
        exit 1
    fi
    
    # Check for existing output file
    if [[ -f "$SCRIPT_DIR/$output_file" ]]; then
        print_warning "Output file already exists: $output_file"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Build cancelled"
            exit 0
        fi
        rm -f "$SCRIPT_DIR/$output_file"
    fi
    
    # Try building with Singularity/Apptainer first
    if check_singularity; then
        build_with_singularity "$SCRIPT_DIR/$def_file" "$SCRIPT_DIR/$output_file"
    elif check_docker; then
        print_warning "Singularity/Apptainer not found, using Docker method"
        build_with_docker "$def_file" "$output_file"
    else
        print_error "Neither Singularity/Apptainer nor Docker found!"
        echo ""
        echo "Please install one of:"
        echo "  • Apptainer: https://apptainer.org/docs/admin/main/installation.html"
        echo "  • Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # Verify build
    if [[ -f "$SCRIPT_DIR/$output_file" ]]; then
        print_success "Build complete!"
        echo ""
        print_header "Build Information"
        ls -lh "$SCRIPT_DIR/$output_file"
        echo ""
        
        # Run tests if available
        print_info "Running tests..."
        if check_singularity; then
            "$SINGULARITY_CMD" test "$SCRIPT_DIR/$output_file" || print_warning "Some tests failed"
        fi
        
        echo ""
        print_header "Next Steps"
        echo ""
        echo "1. Test the image:"
        echo "   $SINGULARITY_CMD shell $output_file"
        echo ""
        echo "2. Run the image:"
        echo "   $SINGULARITY_CMD run $output_file"
        echo ""
        echo "3. Deploy to MUXI Server:"
        echo "   • Copy $output_file to your server"
        echo "   • Update ~/.muxi-server/config.yaml:"
        echo "       formations:"
        echo "         runtime_type: \"singularity\""
        echo "         singularity_image: \"/path/to/$output_file\""
        echo ""
        print_success "All done! 🚀"
    else
        print_error "Build failed - output file not created"
        exit 1
    fi
}

# Show usage
show_usage() {
    cat << EOF
MUXI Runtime SIF Builder

Usage:
  $0 [TYPE] [OUTPUT]

Build Types:
  basic       - Basic runtime (default, ~2GB)
  production  - Production with services (~3GB)

Examples:
  $0                              # Build basic runtime
  $0 basic                        # Build basic runtime
  $0 production                   # Build production runtime
  $0 basic my-custom.sif          # Custom output name
  $0 production muxi-prod.sif     # Production with custom name

Options:
  -h, --help    Show this help message

Requirements:
  • Apptainer/Singularity (preferred)
  • Docker (fallback method)

For more information, see SIF-GUIDE.md

EOF
}

# Parse arguments
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    show_usage
    exit 0
fi

# Change to script directory
cd "$SCRIPT_DIR"

# Run build
build_sif "$BUILD_TYPE" "$OUTPUT_NAME"
