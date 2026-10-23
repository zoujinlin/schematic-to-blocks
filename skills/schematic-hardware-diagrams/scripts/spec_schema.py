"""Validate the JSON Schema keyword subset used by this package, without dependencies.

This is deliberately not a general JSON Schema service. The bundled schema may
also be checked by any Draft 2020-12 validator. External references are forbidden.
"""
import json
import re


class SchemaError(ValueError):
    def __init__(self, message, path):
        self.absolute_path = path
        self.message = message
        super().__init__(message)


def validate(value, schema):
    kinds = {'object': lambda v: isinstance(v, dict), 'array': lambda v: isinstance(v, list),
             'string': lambda v: isinstance(v, str), 'boolean': lambda v: isinstance(v, bool),
             'null': lambda v: v is None, 'integer': lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
             'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
    supported = {'$schema', '$defs', '$ref', 'title', 'description', 'type', 'required', 'properties',
                 'additionalProperties', 'items', 'minItems', 'maxItems', 'uniqueItems', 'minLength',
                 'pattern', 'enum', 'const', 'minimum', 'exclusiveMinimum'}

    def check(item, rule, path):
        def fail(message):
            raise SchemaError(message, path)
        unknown = set(rule) - supported
        if unknown:
            raise ValueError('Unsupported bundled schema keywords: ' + ', '.join(sorted(unknown)))
        if '$ref' in rule:
            reference = rule['$ref']
            if not reference.startswith('#/'):
                raise ValueError('Only local bundled schema references are supported')
            target = schema
            for key in reference[2:].split('/'):
                target = target[key.replace('~1', '/').replace('~0', '~')]
            check(item, target, path)
        expected = rule.get('type')
        if expected is not None:
            allowed = [expected] if isinstance(expected, str) else expected
            if not any(kinds[k](item) for k in allowed):
                fail('Expected ' + ' or '.join(allowed) + ', got ' + type(item).__name__)
        if 'enum' in rule and item not in rule['enum']:
            fail('Value must be one of ' + repr(rule['enum']))
        if 'const' in rule and (isinstance(item, bool) != isinstance(rule['const'], bool) or item != rule['const']):
            fail('Value must equal ' + repr(rule['const']))
        if isinstance(item, dict):
            for key in rule.get('required', []):
                if key not in item:
                    fail('Required property is missing: ' + key)
            for key, val in item.items():
                if key in rule.get('properties', {}):
                    check(val, rule['properties'][key], path + [key])
                else:
                    additional = rule.get('additionalProperties', True)
                    if additional is False:
                        fail('Unexpected property: ' + key)
                    if isinstance(additional, dict):
                        check(val, additional, path + [key])
        if isinstance(item, list):
            if len(item) < rule.get('minItems', 0) or len(item) > rule.get('maxItems', float('inf')):
                fail('Array length violates minItems/maxItems')
            if rule.get('uniqueItems'):
                encoded = [json.dumps(v, sort_keys=True, ensure_ascii=False) for v in item]
                if len(set(encoded)) != len(encoded):
                    fail('Array items must be unique')
            if 'items' in rule:
                for index, val in enumerate(item):
                    check(val, rule['items'], path + [index])
        if isinstance(item, str):
            if len(item) < rule.get('minLength', 0):
                fail('String is shorter than minLength')
            if 'pattern' in rule and re.search(rule['pattern'], item) is None:
                fail('String does not match pattern ' + rule['pattern'])
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            if 'minimum' in rule and item < rule['minimum']:
                fail('Number is below minimum ' + str(rule['minimum']))
            if 'exclusiveMinimum' in rule and item <= rule['exclusiveMinimum']:
                fail('Number must exceed ' + str(rule['exclusiveMinimum']))
    check(value, schema, [])
