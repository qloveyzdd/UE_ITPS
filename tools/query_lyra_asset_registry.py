import json
import os
import traceback

import unreal


OUTPUT_PATH = os.path.join(
    unreal.Paths.project_dir(),
    "..",
    ".planning",
    "evidence",
    "lyra-5.6.1",
    "asset-registry-slice.json",
)

TARGETS = {
    "game_instance": "/Game/B_LyraGameInstance",
    "default_game_mode": "/Game/B_LyraGameMode",
    "default_editor_map": "/Game/System/DefaultEditorMap/L_DefaultEditorOverview",
    "front_end_map": "/Game/System/FrontEnd/Maps/L_LyraFrontEnd",
    "shooter_gym_map": "/ShooterCore/Maps/L_ShooterGym",
    "expanse_map": "/ShooterMaps/Maps/L_Expanse",
    "convolution_map": "/ShooterMaps/Maps/L_Convolution_Blockout",
    "default_experience": "/Game/System/Experiences/B_LyraDefaultExperience",
    "front_end_experience": "/Game/System/FrontEnd/B_LyraFrontEnd_Experience",
    "empty_pawn_data": "/Game/Characters/Heroes/EmptyPawnData/DefaultPawnData_EmptyPawn",
    "simple_pawn_data": "/Game/Characters/Heroes/SimplePawnData/SimplePawnData",
    "shooter_pawn_data": "/ShooterCore/Game/HeroData_ShooterGame",
    "elimination_experience": "/ShooterCore/Experiences/B_ShooterGame_Elimination",
    "control_points_experience": "/ShooterCore/Experiences/B_LyraShooterGame_ControlPoints",
    "shared_input_action_set": "/ShooterCore/Experiences/LAS_ShooterGame_SharedInput",
    "standard_components_action_set": "/ShooterCore/Experiences/LAS_ShooterGame_StandardComponents",
    "standard_hud_action_set": "/ShooterCore/Experiences/LAS_ShooterGame_StandardHUD",
}

DEFAULT_PROPERTIES = (
    "game_features_to_enable",
    "default_pawn_data",
    "actions",
    "action_sets",
    "pawn_class",
    "ability_sets",
    "tag_relationship_mapping",
    "input_config",
    "default_camera_mode",
    "map_id",
    "experience_id",
    "extra_args",
    "is_default_experience",
    "show_in_front_end",
    "record_replay",
    "max_player_count",
)


def make_options(**enabled):
    options = unreal.AssetRegistryDependencyOptions()
    for name in (
        "include_soft_package_references",
        "include_hard_package_references",
        "include_searchable_names",
        "include_soft_management_references",
        "include_hard_management_references",
    ):
        options.set_editor_property(name, enabled.get(name, False))
    return options


DEPENDENCY_QUERIES = {
    "hard_package": make_options(include_hard_package_references=True),
    "soft_package": make_options(include_soft_package_references=True),
    "hard_manage": make_options(include_hard_management_references=True),
    "soft_manage": make_options(include_soft_management_references=True),
}

COUNT_ONLY_TARGETS = {"expanse_map", "convolution_map"}


def json_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "primary_asset_type") and hasattr(
        value, "primary_asset_name"
    ):
        asset_type = value.primary_asset_type
        return {
            "type": str(asset_type.name),
            "name": str(value.primary_asset_name),
        }
    if hasattr(value, "get_path_name"):
        return value.get_path_name()
    if hasattr(value, "items"):
        return {str(key): json_value(item) for key, item in value.items()}
    if hasattr(value, "__iter__"):
        return [json_value(item) for item in value]
    return str(value)


def read_defaults(package_name, asset_name):
    asset = unreal.load_object(None, f"{package_name}.{asset_name}")
    if asset is None:
        return None

    defaults = asset
    result = {}
    if hasattr(asset, "generated_class"):
        generated_class = asset.generated_class()
        defaults = unreal.get_default_object(generated_class)
        result["generated_class"] = generated_class.get_path_name()

    for property_name in DEFAULT_PROPERTIES:
        try:
            result[property_name] = json_value(
                defaults.get_editor_property(property_name)
            )
        except Exception:
            pass
    return result


def query_target(registry, key, package_name):
    assets = registry.get_assets_by_package_name(package_name, True)
    asset_rows = []
    for asset in assets:
        asset_name = str(asset.asset_name)
        class_path = asset.asset_class_path
        row = {
            "asset_name": asset_name,
            "class": (
                f"{class_path.package_name}.{class_path.asset_name}"
            ),
            "object_path": f"{package_name}.{asset_name}",
        }
        if str(class_path.asset_name) == "Blueprint":
            registry_tags = {}
            for tag_name in ("GeneratedClass", "ParentClass", "NativeParentClass"):
                value = unreal.AssetRegistryHelpers.get_tag_value(asset, tag_name)
                if value:
                    registry_tags[tag_name] = value
            row["registry_tags"] = registry_tags
        defaults = read_defaults(package_name, asset_name)
        if defaults:
            row["defaults"] = defaults
        asset_rows.append(row)

    dependencies = {}
    dependency_counts = {}
    for query_name, options in DEPENDENCY_QUERIES.items():
        values = sorted(
            str(name) for name in registry.get_dependencies(package_name, options)
        )
        dependency_counts[query_name] = len(values)
        if key not in COUNT_ONLY_TARGETS:
            dependencies[query_name] = values

    result = {
        "package": package_name,
        "exists": bool(asset_rows),
        "assets": asset_rows,
        "direct_dependency_counts": dependency_counts,
        "direct_dependencies": dependencies,
    }
    if key in COUNT_ONLY_TARGETS:
        result["direct_dependencies_omitted"] = "count-only map comparison"
    return result


def query_user_facing_experiences(registry):
    rows = []
    for root in ("/Game", "/ShooterCore", "/ShooterMaps"):
        for asset in registry.get_assets_by_path(root, True, True):
            if str(asset.asset_class_path.asset_name) != "LyraUserFacingExperienceDefinition":
                continue
            package_name = str(asset.package_name)
            asset_name = str(asset.asset_name)
            rows.append(
                {
                    "package": package_name,
                    "asset_name": asset_name,
                    "defaults": read_defaults(package_name, asset_name),
                }
            )
    return sorted(rows, key=lambda row: row["package"])


def main():
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    registry.scan_paths_synchronous(
        ["/Game", "/ShooterCore", "/ShooterMaps"], True, True
    )

    result = {
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "project_dir": unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_dir()
        ),
        "targets": {},
        "user_facing_experiences": query_user_facing_experiences(registry),
    }
    for key, package_name in TARGETS.items():
        result["targets"][key] = query_target(registry, key, package_name)

    output_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
    unreal.log(f"LYRA_REGISTRY_QUERY_OK: {output_path}")


try:
    main()
except Exception:
    unreal.log_error("LYRA_REGISTRY_QUERY_FAILED\n" + traceback.format_exc())
    raise
