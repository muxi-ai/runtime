# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Extensions - Framework Extension System
# Description:  Base extension system for extending framework functionality
# Role:         Enables pluggable functionality and framework customization
# Usage:        Used to create and register extensions to the framework
# Author:       Muxi Framework Team
#
# The extensions system provides a mechanism for extending the Muxi framework
# with additional functionality in a modular way. It includes:
#
# 1. Extension Registration
#    - Class-based registration system
#    - Name-based lookup mechanism
#    - Central registry for all extensions
#
# 2. Standardized Interface
#    - Common initialization pattern
#    - Consistent extension lifecycle
#    - Clean integration with the framework
#
# 3. Discoverability
#    - Self-documenting extension system
#    - Ability to list available extensions
#    - Easy extension instantiation
#
# Extensions can provide various types of functionality such as:
# - Additional memory backends
# - Custom knowledge sources
# - Vector storage implementations
# - Authentication providers
# - Custom agent behaviors
#
# Example usage:
#
#   # Define a custom extension
#   @Extension.register
#   class CustomVectorStorage(Extension):
#       name = "custom_vector_storage"
#
#       @classmethod
#       def init(cls, connection_string, **kwargs):
#           # Initialize the extension
#           return CustomVectorStorageInstance(connection_string)
#
#   # Use the extension
#   vector_storage_cls = Extension.get("custom_vector_storage")
#   vector_storage = vector_storage_cls.init(
#       connection_string="redis://localhost:6379"
#   )
#
# Extensions can be loaded dynamically based on configuration settings,
# allowing the framework to be extended without code changes.
# =============================================================================

# Graceful import for observability
try:
    from ..observability import ObservabilityManager, EventType, EventLevel
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False


class Extension:
    """
    Base class for all MUXI extensions.

    Extensions provide additional functionality to the MUXI framework and
    can be loaded either declaratively or programmatically. This base class
    provides the registration mechanism, discovery functions, and defines the
    interface that all extensions must implement.

    Extensions use a class-based registration system where extension classes
    register themselves with a unique name. This allows extensions to be
    looked up by name and instantiated dynamically based on configuration.
    """

    name = None  # Must be defined by each extension subclass
    _registry = {}  # Global registry of all registered extensions

    @classmethod
    def register(cls, extension_cls):
        """
        Register an extension class in the global registry.

        This method can be used as a decorator to register extension classes.
        Each extension must have a unique name defined as a class attribute.
        The registry allows extensions to be looked up by name at runtime.

        Args:
            extension_cls: The extension class to register. Must have a 'name'
                class attribute that uniquely identifies this extension.

        Returns:
            The registered extension class (enabling decorator syntax).

        Raises:
            ValueError: If the extension class doesn't define a 'name' attribute.
        """
        # Observability: Extension registration started
        if OBSERVABILITY_AVAILABLE:
            try:
                obs_manager = ObservabilityManager.get_instance()
                obs_manager.log_event(
                    event_type=EventType.EXTENSION_REGISTRATION_STARTED,
                    level=EventLevel.INFO,
                    message=(f"Starting extension registration for "
                             f"{extension_cls.__name__}"),
                    data={
                        "extension_class": extension_cls.__name__,
                        "extension_name": getattr(extension_cls, 'name', None),
                        "registry_size_before": len(cls._registry)
                    }
                )
            except Exception:
                pass  # Don't let observability failures break functionality

        try:
            if not extension_cls.name:
                error_msg = "Extension must define a 'name' class attribute"

                # Observability: Extension registration failed
                if OBSERVABILITY_AVAILABLE:
                    try:
                        obs_manager.log_event(
                            event_type=EventType.EXTENSION_REGISTRATION_COMPLETED,
                            level=EventLevel.ERROR,
                            message=(f"Extension registration failed for "
                                     f"{extension_cls.__name__}: {error_msg}"),
                            data={
                                "extension_class": extension_cls.__name__,
                                "error": error_msg,
                                "success": False
                            }
                        )
                    except Exception:
                        pass

                raise ValueError(error_msg)

            cls._registry[extension_cls.name] = extension_cls

            # Observability: Extension registration completed successfully
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_REGISTRATION_COMPLETED,
                        level=EventLevel.INFO,
                        message=f"Extension registration completed for {extension_cls.__name__}",
                        data={
                            "extension_class": extension_cls.__name__,
                            "extension_name": extension_cls.name,
                            "registry_size_after": len(cls._registry),
                            "success": True
                        }
                    )
                except Exception:
                    pass

            return extension_cls

        except Exception as e:
            # Observability: Extension registration failed with exception
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_REGISTRATION_COMPLETED,
                        level=EventLevel.ERROR,
                        message=(f"Extension registration failed for "
                                 f"{extension_cls.__name__}: {str(e)}"),
                        data={
                            "extension_class": extension_cls.__name__,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "success": False
                        }
                    )
                except Exception:
                    pass
            raise

    @classmethod
    def get(cls, name):
        """
        Get an extension class by name.

        Retrieves a registered extension class using its unique name.
        This is the primary method for accessing extensions dynamically.

        Args:
            name: The name of the extension to retrieve. This should match
                the 'name' class attribute of the registered extension.

        Returns:
            The extension class if found, or None if no extension with the
            specified name is registered.
        """
        # Observability: Extension retrieval started
        if OBSERVABILITY_AVAILABLE:
            try:
                obs_manager = ObservabilityManager.get_instance()
                obs_manager.log_event(
                    event_type=EventType.EXTENSION_LOOKUP_STARTED,
                    level=EventLevel.DEBUG,
                    message=f"Starting extension lookup for name: {name}",
                    data={
                        "extension_name": name,
                        "registry_size": len(cls._registry),
                        "available_extensions": list(cls._registry.keys())
                    }
                )
            except Exception:
                pass

        try:
            extension_cls = cls._registry.get(name)
            found = extension_cls is not None

            # Observability: Extension retrieval completed
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_LOOKUP_COMPLETED,
                        level=EventLevel.DEBUG,
                        message=(f"Extension lookup completed for name: {name}, "
                                 f"found: {found}"),
                        data={
                            "extension_name": name,
                            "found": found,
                            "extension_class": extension_cls.__name__ if extension_cls else None,
                            "success": True
                        }
                    )
                except Exception:
                    pass

            return extension_cls

        except Exception as e:
            # Observability: Extension retrieval failed
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_LOOKUP_COMPLETED,
                        level=EventLevel.ERROR,
                        message=f"Extension lookup failed for name: {name}: {str(e)}",
                        data={
                            "extension_name": name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "success": False
                        }
                    )
                except Exception:
                    pass
            raise

    @classmethod
    def list(cls):
        """
        List all registered extensions.

        Provides a way to discover all available extensions that have been
        registered with the system.

        Returns:
            A list of strings containing the names of all registered extensions.
            These names can be used with the get() method to retrieve the
            corresponding extension classes.
        """
        # Observability: Extension listing started
        if OBSERVABILITY_AVAILABLE:
            try:
                obs_manager = ObservabilityManager.get_instance()
                obs_manager.log_event(
                    event_type=EventType.EXTENSION_LISTING_STARTED,
                    level=EventLevel.DEBUG,
                    message="Starting extension listing",
                    data={
                        "registry_size": len(cls._registry)
                    }
                )
            except Exception:
                pass

        try:
            extension_names = list(cls._registry.keys())

            # Observability: Extension listing completed
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_LISTING_COMPLETED,
                        level=EventLevel.DEBUG,
                        message=(f"Extension listing completed, found "
                                 f"{len(extension_names)} extensions"),
                        data={
                            "extension_count": len(extension_names),
                            "extension_names": extension_names,
                            "success": True
                        }
                    )
                except Exception:
                    pass

            return extension_names

        except Exception as e:
            # Observability: Extension listing failed
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_LISTING_COMPLETED,
                        level=EventLevel.ERROR,
                        message=f"Extension listing failed: {str(e)}",
                        data={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "success": False
                        }
                    )
                except Exception:
                    pass
            raise

    @classmethod
    def init(cls, **kwargs):
        """
        Initialize the extension.

        This abstract method must be implemented by each extension subclass.
        It handles the initialization logic for the extension, taking any
        configuration parameters needed to set up the extension.

        Args:
            **kwargs: Extension-specific initialization parameters. These vary
                depending on the specific extension being initialized.

        Returns:
            The initialized extension instance or resource (implementation-specific).

        Raises:
            NotImplementedError: If the extension subclass does not implement this method.
        """
        # Observability: Extension initialization started
        if OBSERVABILITY_AVAILABLE:
            try:
                obs_manager = ObservabilityManager.get_instance()
                obs_manager.log_event(
                    event_type=EventType.EXTENSION_INITIALIZATION_STARTED,
                    level=EventLevel.INFO,
                    message=f"Starting extension initialization for {cls.__name__}",
                    data={
                        "extension_class": cls.__name__,
                        "extension_name": getattr(cls, 'name', None),
                        "kwargs_keys": list(kwargs.keys()),
                        "kwargs_count": len(kwargs)
                    }
                )
            except Exception:
                pass

        try:
            error_msg = f"Extension {cls.__name__} does not implement the init method"

            # Observability: Extension initialization failed (not implemented)
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_INITIALIZATION_COMPLETED,
                        level=EventLevel.ERROR,
                        message=(f"Extension initialization failed for "
                                 f"{cls.__name__}: {error_msg}"),
                        data={
                            "extension_class": cls.__name__,
                            "extension_name": getattr(cls, 'name', None),
                            "error": error_msg,
                            "error_type": "NotImplementedError",
                            "success": False
                        }
                    )
                except Exception:
                    pass

            raise NotImplementedError(error_msg)

        except Exception as e:
            # Observability: Extension initialization failed with exception
            if OBSERVABILITY_AVAILABLE:
                try:
                    obs_manager.log_event(
                        event_type=EventType.EXTENSION_INITIALIZATION_COMPLETED,
                        level=EventLevel.ERROR,
                        message=(f"Extension initialization failed for "
                                 f"{cls.__name__}: {str(e)}"),
                        data={
                            "extension_class": cls.__name__,
                            "extension_name": getattr(cls, 'name', None),
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "success": False
                        }
                    )
                except Exception:
                    pass
            raise
