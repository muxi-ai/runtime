#!/usr/bin/env python3
"""Phase 6 Final Comprehensive Validation Test"""

from muxi.runtime.config.validation import FormationValidator
import tempfile
import yaml

def main():
    validator = FormationValidator()

    # Phase 6 comprehensive formation with ALL SCHEMA_GUIDE.md features
    formation = {
        'schema': '1.0.0',
        'id': 'phase6-final-comprehensive',
        'description': 'Phase 6 final comprehensive validation test',
        'author': 'Phase 6 Team <phase6@muxi.com>',
        'url': 'https://muxi.com/phase6',
        'license': 'Apache-2.0',
        'version': '6.0.0',
        'system_message': 'Phase 6 comprehensive system message',

        # Complete authentication
        'auth': {
            'api_keys': {
                'admin_key': '${{ secrets.PHASE6_ADMIN_KEY }}',
                'user_key': '${{ secrets.PHASE6_USER_KEY }}'
            }
        },

        # Complete LLM configuration with all capabilities
        'llm': {
            'settings': {
                'temperature': 0.7,
                'max_tokens': 2000,
                'timeout_seconds': 45
            },
            'api_keys': {
                'openai': '${{ secrets.PHASE6_OPENAI_KEY }}',
                'anthropic': '${{ secrets.PHASE6_ANTHROPIC_KEY }}',
                'other': '${{ secrets.PHASE6_OTHER_KEY }}'
            },
            'models': [
                {
                    'text': 'openai/gpt-4o',
                    'settings': {'temperature': 0.6}
                },
                {
                    'vision': 'openai/gpt-4o',
                    'settings': {
                        'image': {
                            'max_size_mb': 10,
                            'preprocessing': {
                                'resize': True,
                                'max_width': 1024,
                                'max_height': 1024
                            }
                        }
                    }
                },
                {
                    'audio': 'openai/whisper-1',
                    'settings': {
                        'max_size_mb': 20,
                        'language': 'auto'
                    }
                },
                {
                    'documents': 'openai/gpt-4o',
                    'settings': {
                        'max_size_mb': 30,
                        'extraction': {
                            'chunk_size': 1000,
                            'overlap': 100
                        }
                    }
                },
                {
                    'embedding': 'openai/text-embedding-3-large',
                    'settings': {'temperature': 0.0}
                }
            ]
        },

        # Complete overlord configuration
        'overlord': {
            'system_message': 'Phase 6 overlord system message',
            'llm': {
                'model': 'anthropic/claude-3-opus',
                'api_key': '${{ secrets.PHASE6_OVERLORD_KEY }}',
                'settings': {
                    'temperature': 0.2,
                    'max_tokens': 3000,
                    'timeout_seconds': 60
                }
            },
            'config': {
                'max_extraction_tokens': 1000,
                'caching': {
                    'enabled': True,
                    'ttl': 7200
                },
                'max_tool_calls': 20,
                'response_format': 'markdown'
            }
        },

        # Complete memory configuration
        'memory': {
            'buffer': {
                'size': 15,
                'multiplier': 10,
                'vector_search': True,
                'vector_dimension': 1536,
                'mode': 'local'
            },
            'long_term': {
                'connection_string': '${{ secrets.PHASE6_DATABASE_URL }}',
                'embedding_model': 'openai/text-embedding-3-large'
            }
        },

        # Complete logging configuration
        'logging': {
            'level': 'info',
            'format': 'jsonl',
            'output': 'stdout',
            'log': ['errors', 'system_health', 'overlord_routing']
        },

        # Complete A2A configuration
        'a2a': {
            'enabled': True,
            'outbound': {
                'enabled': True,
                'registries': ['https://a2a.phase6.com'],
                'default_retry_attempts': 3,
                'default_timeout_seconds': 30,
                'services': []
            },
            'inbound': {
                'enabled': True,
                'port': 8181,
                'trusted_endpoints': ['trusted.phase6.com'],
                'mode': 'api_key',
                'shared_key': '${{ secrets.PHASE6_A2A_KEY }}'
            }
        },

        # Complete MCP configuration
        'mcp': {
            'default_retry_attempts': 3,
            'default_timeout_seconds': 30,
            'servers': []
        },

        # Auto-discovered agents
        'agents': []
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        result = validator.validate(f.name)

    print(f"🎯 Phase 6 Final Comprehensive Test:")
    print(f"   Valid: {result.is_valid}")
    print(f"   Errors: {len(result.errors)}")
    print(f"   Warnings: {len(result.warnings)}")

    if not result.is_valid:
        print("❌ Validation Errors:")
        for error in result.errors[:5]:
            print(f"   - {error}")
    else:
        print("✅ Phase 6 Comprehensive Schema Validation: COMPLETE")
        print("✅ All SCHEMA_GUIDE.md features validated successfully")

    if result.warnings:
        print("⚠️  Warnings:")
        for warning in result.warnings[:3]:
            print(f"   - {warning}")

if __name__ == '__main__':
    main()
