"""
Pydantic模型到OpenAI JSON Schema转换工具
解决Google GenAI SDK和OpenAI API结构化输出的兼容性问题
"""

import json
import logging
from typing import Dict, Any, Type, get_origin, get_args, Union
from pydantic import BaseModel
from pydantic.fields import FieldInfo

logger = logging.getLogger(__name__)


class SchemaConversionError(Exception):
    """Schema转换异常"""
    pass


def pydantic_to_openai_schema(model_class: Type[BaseModel]) -> Dict[str, Any]:
    """
    将Pydantic模型转换为OpenAI API兼容的json_schema格式
    
    Args:
        model_class: Pydantic BaseModel类
        
    Returns:
        OpenAI API兼容的json_schema格式字典
        
    Raises:
        SchemaConversionError: 当转换过程中遇到不支持的字段类型时
    """
    try:
        # 获取Pydantic模型的schema
        pydantic_schema = model_class.model_json_schema()
        
        # 构建OpenAI格式的JSON Schema
        openai_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": model_class.__name__,
                "strict": True,  # 确保严格模式
                "schema": _convert_pydantic_schema_to_openai(pydantic_schema)
            }
        }
        
        logger.debug(f"成功转换Pydantic模型 {model_class.__name__} 为OpenAI JSON Schema")
        return openai_schema
        
    except Exception as e:
        error_msg = f"转换Pydantic模型 {model_class.__name__} 到OpenAI Schema失败: {str(e)}"
        logger.error(error_msg)
        raise SchemaConversionError(error_msg) from e


def _convert_pydantic_schema_to_openai(pydantic_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    转换Pydantic schema为OpenAI兼容格式
    
    Args:
        pydantic_schema: Pydantic生成的JSON Schema
        
    Returns:
        OpenAI兼容的schema格式
    """
    openai_schema = {
        "type": "object",
        "properties": {},
        "required": pydantic_schema.get("required", []),
        "additionalProperties": False  # 禁止额外属性，确保严格模式
    }
    
    # 转换属性
    properties = pydantic_schema.get("properties", {})
    for field_name, field_schema in properties.items():
        try:
            openai_schema["properties"][field_name] = _convert_field_schema(field_schema)
        except Exception as e:
            logger.warning(f"转换字段 {field_name} 时出错: {str(e)}")
            # 继续处理其他字段，但记录警告
            openai_schema["properties"][field_name] = {"type": "string"}
    
    return openai_schema


def _convert_field_schema(field_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    转换单个字段的schema
    
    Args:
        field_schema: Pydantic字段schema
        
    Returns:
        OpenAI兼容的字段schema
    """
    converted = {}
    
    # 处理字段类型
    field_type = field_schema.get("type")
    
    if field_type == "number":
        converted["type"] = "number"
        # 转换数值约束
        if "minimum" in field_schema:
            converted["minimum"] = field_schema["minimum"]
        if "maximum" in field_schema:
            converted["maximum"] = field_schema["maximum"]
        if "exclusiveMinimum" in field_schema:
            converted["exclusiveMinimum"] = field_schema["exclusiveMinimum"]
        if "exclusiveMaximum" in field_schema:
            converted["exclusiveMaximum"] = field_schema["exclusiveMaximum"]
            
    elif field_type == "integer":
        converted["type"] = "integer"
        # 转换整数约束
        if "minimum" in field_schema:
            converted["minimum"] = field_schema["minimum"]
        if "maximum" in field_schema:
            converted["maximum"] = field_schema["maximum"]
            
    elif field_type == "string":
        converted["type"] = "string"
        # 转换字符串约束
        if "minLength" in field_schema:
            converted["minLength"] = field_schema["minLength"]
        if "maxLength" in field_schema:
            converted["maxLength"] = field_schema["maxLength"]
        if "pattern" in field_schema:
            converted["pattern"] = field_schema["pattern"]
        # 处理枚举值（Literal类型）
        if "enum" in field_schema:
            converted["enum"] = field_schema["enum"]
            
    elif field_type == "boolean":
        converted["type"] = "boolean"
        
    elif field_type is None and "enum" in field_schema:
        # 处理Literal类型（枚举）
        converted["type"] = "string"
        converted["enum"] = field_schema["enum"]
        
    elif field_type is None and "anyOf" in field_schema:
        # 处理Union类型，简化处理
        any_of = field_schema["anyOf"]
        if len(any_of) == 1:
            return _convert_field_schema(any_of[0])
        else:
            # 复杂Union类型，默认为string
            logger.warning(f"复杂Union类型暂不完全支持，默认为string: {field_schema}")
            converted["type"] = "string"
            
    else:
        # 未知类型，默认为string
        logger.warning(f"未知字段类型 {field_type}，默认为string")
        converted["type"] = "string"
    
    # 添加描述
    if "description" in field_schema:
        converted["description"] = field_schema["description"]
    
    return converted


def get_schema_for_model(model_class: Type[BaseModel]) -> Dict[str, Any]:
    """
    获取模型的完整schema信息（包含转换前后对比）
    
    Args:
        model_class: Pydantic BaseModel类
        
    Returns:
        包含原始和转换后schema的字典
    """
    try:
        pydantic_schema = model_class.model_json_schema()
        openai_schema = pydantic_to_openai_schema(model_class)
        
        return {
            "model_name": model_class.__name__,
            "pydantic_schema": pydantic_schema,
            "openai_schema": openai_schema,
            "conversion_success": True
        }
    except Exception as e:
        logger.error(f"获取模型 {model_class.__name__} 的schema失败: {str(e)}")
        return {
            "model_name": model_class.__name__,
            "pydantic_schema": None,
            "openai_schema": None,
            "conversion_success": False,
            "error": str(e)
        }


def validate_conversion(model_class: Type[BaseModel]) -> bool:
    """
    验证转换结果的正确性
    
    Args:
        model_class: Pydantic BaseModel类
        
    Returns:
        转换是否成功
    """
    try:
        openai_schema = pydantic_to_openai_schema(model_class)
        
        # 基本验证
        assert "json_schema" in openai_schema, "缺少json_schema字段"
        assert "schema" in openai_schema["json_schema"], "缺少schema字段"
        assert openai_schema["json_schema"]["strict"] is True, "strict模式未启用"
        
        schema = openai_schema["json_schema"]["schema"]
        assert schema["type"] == "object", "根类型必须为object"
        assert schema["additionalProperties"] is False, "必须禁止额外属性"
        assert "properties" in schema, "缺少properties字段"
        
        logger.info(f"模型 {model_class.__name__} 转换验证成功")
        return True
        
    except Exception as e:
        logger.error(f"模型 {model_class.__name__} 转换验证失败: {str(e)}")
        return False


# 工具函数：快速测试转换结果
def test_conversion_with_example(model_class: Type[BaseModel]) -> None:
    """
    测试转换结果并打印示例
    
    Args:
        model_class: Pydantic BaseModel类
    """
    try:
        print(f"\n=== 测试 {model_class.__name__} 转换 ===")
        
        # 转换
        openai_schema = pydantic_to_openai_schema(model_class)
        
        # 验证
        is_valid = validate_conversion(model_class)
        print(f"转换验证: {'✅ 通过' if is_valid else '❌ 失败'}")
        
        # 打印转换结果
        print("\nOpenAI JSON Schema:")
        print(json.dumps(openai_schema, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ 转换测试失败: {str(e)}")