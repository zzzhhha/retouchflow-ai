local Json = {}

local escape_map = {
    ['"'] = '\\"',
    ["\\"] = "\\\\",
    ["\b"] = "\\b",
    ["\f"] = "\\f",
    ["\n"] = "\\n",
    ["\r"] = "\\r",
    ["\t"] = "\\t",
}

local function escape_char(char)
    return escape_map[char] or string.format("\\u%04x", char:byte())
end

local function is_array(value)
    local max = 0
    local count = 0
    for key, _ in pairs(value) do
        if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
            return false
        end
        if key > max then
            max = key
        end
        count = count + 1
    end
    return max == count
end

function Json.encode(value)
    local value_type = type(value)
    if value_type == "nil" then
        return "null"
    elseif value_type == "boolean" then
        return value and "true" or "false"
    elseif value_type == "number" then
        return tostring(value)
    elseif value_type == "string" then
        return '"' .. value:gsub('[%z\1-\31\\"]', escape_char) .. '"'
    elseif value_type == "table" then
        local chunks = {}
        if is_array(value) then
            for index = 1, #value do
                chunks[#chunks + 1] = Json.encode(value[index])
            end
            return "[" .. table.concat(chunks, ",") .. "]"
        end
        for key, item in pairs(value) do
            chunks[#chunks + 1] = Json.encode(tostring(key)) .. ":" .. Json.encode(item)
        end
        return "{" .. table.concat(chunks, ",") .. "}"
    end
    error("Unsupported JSON value type: " .. value_type)
end

local Parser = {}
Parser.__index = Parser

function Parser:new(text)
    return setmetatable({ text = text, pos = 1, len = #text }, Parser)
end

function Parser:peek()
    return self.text:sub(self.pos, self.pos)
end

function Parser:next()
    local char = self:peek()
    self.pos = self.pos + 1
    return char
end

function Parser:skip_ws()
    while self.pos <= self.len do
        local char = self:peek()
        if char ~= " " and char ~= "\n" and char ~= "\r" and char ~= "\t" then
            break
        end
        self.pos = self.pos + 1
    end
end

function Parser:expect(expected)
    local actual = self:next()
    if actual ~= expected then
        error("Expected '" .. expected .. "' at JSON position " .. tostring(self.pos - 1))
    end
end

function Parser:parse_string()
    self:expect('"')
    local chunks = {}
    while self.pos <= self.len do
        local char = self:next()
        if char == '"' then
            return table.concat(chunks)
        elseif char == "\\" then
            local escaped = self:next()
            if escaped == '"' or escaped == "\\" or escaped == "/" then
                chunks[#chunks + 1] = escaped
            elseif escaped == "b" then
                chunks[#chunks + 1] = "\b"
            elseif escaped == "f" then
                chunks[#chunks + 1] = "\f"
            elseif escaped == "n" then
                chunks[#chunks + 1] = "\n"
            elseif escaped == "r" then
                chunks[#chunks + 1] = "\r"
            elseif escaped == "t" then
                chunks[#chunks + 1] = "\t"
            elseif escaped == "u" then
                local hex = self.text:sub(self.pos, self.pos + 3)
                self.pos = self.pos + 4
                local code = tonumber(hex, 16) or 63
                if code < 128 then
                    chunks[#chunks + 1] = string.char(code)
                else
                    chunks[#chunks + 1] = "?"
                end
            else
                error("Invalid JSON escape at position " .. tostring(self.pos - 1))
            end
        else
            chunks[#chunks + 1] = char
        end
    end
    error("Unterminated JSON string")
end

function Parser:parse_number()
    local start = self.pos
    local char = self:peek()
    while char:match("[%d%+%-%e%E%.]") do
        self.pos = self.pos + 1
        if self.pos > self.len then
            break
        end
        char = self:peek()
    end
    local number = tonumber(self.text:sub(start, self.pos - 1))
    if number == nil then
        error("Invalid JSON number at position " .. tostring(start))
    end
    return number
end

function Parser:parse_array()
    self:expect("[")
    local result = {}
    self:skip_ws()
    if self:peek() == "]" then
        self:next()
        return result
    end
    while true do
        result[#result + 1] = self:parse_value()
        self:skip_ws()
        local char = self:next()
        if char == "]" then
            return result
        elseif char ~= "," then
            error("Expected ',' or ']' at JSON position " .. tostring(self.pos - 1))
        end
    end
end

function Parser:parse_object()
    self:expect("{")
    local result = {}
    self:skip_ws()
    if self:peek() == "}" then
        self:next()
        return result
    end
    while true do
        self:skip_ws()
        local key = self:parse_string()
        self:skip_ws()
        self:expect(":")
        result[key] = self:parse_value()
        self:skip_ws()
        local char = self:next()
        if char == "}" then
            return result
        elseif char ~= "," then
            error("Expected ',' or '}' at JSON position " .. tostring(self.pos - 1))
        end
    end
end

function Parser:parse_literal(literal, value)
    if self.text:sub(self.pos, self.pos + #literal - 1) ~= literal then
        error("Expected " .. literal .. " at JSON position " .. tostring(self.pos))
    end
    self.pos = self.pos + #literal
    return value
end

function Parser:parse_value()
    self:skip_ws()
    local char = self:peek()
    if char == '"' then
        return self:parse_string()
    elseif char == "{" then
        return self:parse_object()
    elseif char == "[" then
        return self:parse_array()
    elseif char == "t" then
        return self:parse_literal("true", true)
    elseif char == "f" then
        return self:parse_literal("false", false)
    elseif char == "n" then
        return self:parse_literal("null", nil)
    end
    return self:parse_number()
end

function Json.decode(text)
    local parser = Parser:new(text)
    local value = parser:parse_value()
    parser:skip_ws()
    if parser.pos <= parser.len then
        error("Trailing content after JSON value")
    end
    return value
end

return Json
