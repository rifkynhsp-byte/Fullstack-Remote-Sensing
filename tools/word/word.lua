--[[
word.lua: shapes the Word edition of the book.

  1. Removes what only works on the web: runnable Python cells (.py-live),
     platform widgets (.lms-*), and the "change the chart yourself" prompts.
     Raw HTML (web maps, quizzes) is already dropped by the docx writer.
  2. Numbers every captioned figure and table across the whole book and
     writes the List of Figures and List of Tables into the placeholders
     ::: {#list-of-figures} ::: and ::: {#list-of-tables} ::: in the front matter.
--]]

local WEB_ONLY = { ["py-live"] = true, ["py-live-intro"] = true, ["web-only"] = true }

local function web_only(el)
  for _, c in ipairs(el.classes) do
    if WEB_ONLY[c] or c:match("^lms%-") then return true end
  end
  return false
end

local figures, tables = {}, {}
local chapter = ""

local function caption_text(blocks)
  return pandoc.utils.stringify(blocks or {}):gsub("%s+", " ")
end

local LABELS = { fig = "Figure", tab = "Table" }

-- Walks the blocks in reading order, numbers captioned figures and tables,
-- writes the number into the caption, and remembers it for the lists.
local function prefix(caption, text)
  local first = caption.long[1]
  if first and (first.t == "Plain" or first.t == "Para") then
    table.insert(first.content, 1, pandoc.Space())
    table.insert(first.content, 1, pandoc.Strong(pandoc.Str(text)))
  end
end

local function collect(blocks)
  for _, b in ipairs(blocks) do
    if b.t == "Header" and b.level == 1 then
      chapter = pandoc.utils.stringify(b.content)
    elseif b.t == "Figure" then
      local cap = caption_text(b.caption.long)
      if cap ~= "" then
        table.insert(figures, { chapter = chapter, caption = cap })
        prefix(b.caption, LABELS.fig .. " " .. #figures .. ".")
      end
    elseif b.t == "Table" then
      local cap = caption_text(b.caption.long)
      if cap ~= "" then
        table.insert(tables, { chapter = chapter, caption = cap })
        prefix(b.caption, LABELS.tab .. " " .. #tables .. ".")
      end
    elseif b.t == "Div" or b.t == "BlockQuote" then
      collect(b.content)
    end
  end
end

local function short(text, n)
  if #text <= n then return text end
  local cut = text:sub(1, n):gsub("%s+%S*$", "")
  return cut .. "…"
end

local function list_blocks(items, label)
  local out = {}
  if #items == 0 then return out end
  local current = nil
  for i, it in ipairs(items) do
    if it.chapter ~= current then
      current = it.chapter
      table.insert(out, pandoc.Para({ pandoc.Strong(pandoc.Str(current)) }))
    end
    table.insert(out, pandoc.Para({ pandoc.Str(label .. " " .. i .. ". " .. short(it.caption, 160)) }))
  end
  return out
end

-- An explicit page break before every chapter title. A "page break before"
-- setting in the Heading 1 style alone is ignored by many viewers.
local PAGE_BREAK = pandoc.RawBlock("openxml",
  '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

function Pandoc(doc)
  doc = doc:walk({
    Header = function(el)
      if el.level == 1 then return { PAGE_BREAK, el } end
    end,
  })
  -- 1. strip web-only blocks
  doc = doc:walk({
    Div = function(el) if web_only(el) then return {} end end,
    CodeBlock = function(el) if web_only(el) then return {} end end,
  })
  -- 2. lists
  local lang = (doc.meta.lang and pandoc.utils.stringify(doc.meta.lang)) or "en"
  if lang == "id" then LABELS = { fig = "Gambar", tab = "Tabel" } end
  local fig_label, tab_label = LABELS.fig, LABELS.tab
  collect(doc.blocks)
  doc = doc:walk({
    Div = function(el)
      if el.identifier == "list-of-figures" then
        return pandoc.Div(list_blocks(figures, fig_label))
      elseif el.identifier == "list-of-tables" then
        return pandoc.Div(list_blocks(tables, tab_label))
      end
    end,
  })
  return doc
end
