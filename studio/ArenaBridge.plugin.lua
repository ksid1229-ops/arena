-- Install as a local Studio plugin. No arbitrary command execution or auto-approval.
local Http = game:GetService("HttpService")
local History = game:GetService("ChangeHistoryService")
local Scripts = game:GetService("ScriptEditorService")
local Run = game:GetService("RunService")
local toolbar = plugin:CreateToolbar("Arena Bridge")
local toggle = toolbar:CreateButton("Bridge", "Open Arena Bridge", "")
local widget = plugin:CreateDockWidgetPluginGui("ArenaBridgeV1", DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, false, false, 440, 650, 320, 450))
widget.Title = "Arena • Studio Bridge"
local function control(class, y, height, text)
    local item = Instance.new(class)
    item.Size = UDim2.new(1, -20, 0, height)
    item.Position = UDim2.fromOffset(10, y)
    item.BackgroundColor3 = Color3.fromRGB(35, 39, 48)
    item.TextColor3 = Color3.fromRGB(240, 242, 248)
    item.TextSize = 14
    item.Font = Enum.Font.Code
    item.Text = text
    if class == "TextBox" then item.ClearTextOnFocus = false end
    item.Parent = widget
    return item
end
local urlBox = control("TextBox", 10, 40, "https://YOUR-ARENA-PREVIEW-HOST")
local tokenBox = control("TextBox", 60, 40, "Paste bridge token (not saved)")
local connect = control("TextButton", 110, 35, "Connect / Disconnect")
local status = control("TextLabel", 155, 50, "Disconnected. Use a backup place.")
status.TextWrapped = true
local review = control("TextBox", 215, 300, "Requests appear here. Inspect requests also need approval.")
review.MultiLine = true
review.TextWrapped = true
review.TextXAlignment = Enum.TextXAlignment.Left
review.TextYAlignment = Enum.TextYAlignment.Top
review.TextEditable = false
local approve = control("TextButton", 525, 35, "Approve this request")
local reject = control("TextButton", 570, 35, "Reject this request")
local connected, busy = false, false
local endpoint, token, pending, outbox
local session = tostring(game.PlaceId) .. ":" .. Http:GenerateGUID(false)
local roots = { Workspace=true, ReplicatedStorage=true, ServerStorage=true, ServerScriptService=true, StarterGui=true, StarterPack=true, StarterPlayer=true, Lighting=true, SoundService=true }
local classes = { Folder=true, Model=true, Part=true, SpawnLocation=true, Script=true, LocalScript=true, ModuleScript=true, ScreenGui=true, Frame=true, TextLabel=true, TextButton=true, TextBox=true, ImageLabel=true, ImageButton=true, UIListLayout=true, UIPadding=true, UICorner=true, Attachment=true, PointLight=true, SurfaceLight=true, SpotLight=true, Sound=true }
local properties = { Name=true, Value=true, Anchored=true, CanCollide=true, CanTouch=true, CanQuery=true, Transparency=true, Reflectance=true, Color=true, Material=true, Size=true, Position=true, CFrame=true, Orientation=true, Shape=true, Text=true, TextColor3=true, TextSize=true, BackgroundColor3=true, BackgroundTransparency=true, BorderSizePixel=true, Visible=true, Enabled=true, Disabled=true, ResetOnSpawn=true, DisplayOrder=true, LayoutOrder=true, AnchorPoint=true, Image=true, ImageTransparency=true, Brightness=true, Range=true, SoundId=true, Volume=true, Looped=true }
local function resolve(path)
    assert(type(path) == "table" and roots[path[1]], "Root service not allowed")
    local node = game:GetService(path[1])
    for i = 2, #path do
        local match
        for _, child in node:GetChildren() do
            if child.Name == path[i] then
                assert(not match, "Ambiguous path: duplicate names")
                match = child
            end
        end
        assert(match, "Instance not found: " .. tostring(path[i]))
        node = match
    end
    return node
end
local function decode(value)
    if type(value) ~= "table" then return value end
    local v = value.value
    assert(type(v) == "table", "Typed value requires value array")
    if value.type == "Vector3" then return Vector3.new(table.unpack(v)) end
    if value.type == "Vector2" then return Vector2.new(table.unpack(v)) end
    if value.type == "Color3" then return Color3.new(table.unpack(v)) end
    if value.type == "UDim2" then return UDim2.new(table.unpack(v)) end
    if value.type == "UDim" then return UDim.new(table.unpack(v)) end
    if value.type == "CFrame" then assert(#v == 3 or #v == 12, "CFrame needs 3 or 12 numbers"); return CFrame.new(table.unpack(v)) end
    if value.type == "Enum" then return Enum[v[1]][v[2]] end
    error("Unknown typed value")
end
local function apply(node, values)
    local decoded = {}
    for key, value in pairs(values or {}) do
        assert(properties[key], "Property not allowed: " .. key)
        decoded[key] = decode(value)
    end
    for key, value in pairs(decoded) do node[key] = value end
end
local function execute(command)
    assert(not Run:IsRunning(), "Stop playtest before using bridge")
    local node = resolve(command.path)
    local args = command.args or {}
    if command.op == "inspect" then
        local children = {}
        for i, child in node:GetChildren() do
            if i > 200 then break end
            table.insert(children, {name=child.Name, class=child.ClassName})
        end
        local result = {name=node.Name, class=node.ClassName, children=children, childCount=#node:GetChildren()}
        if node:IsA("LuaSourceContainer") then result.source = Scripts:GetEditorSource(node) end
        return result
    end
    local recording = History:TryBeginRecording("ArenaBridge", "Arena: " .. command.op)
    assert(recording, "Unable to start undo recording")
    local ok, result = pcall(function()
        if command.op == "create" then
            assert(classes[args.class], "Class not allowed")
            assert(type(args.name) == "string" and #args.name > 0, "name required")
            assert(not node:FindFirstChild(args.name), "Name already exists")
            local child = Instance.new(args.class)
            local success, err = pcall(function()
                -- New executable scripts start disabled. Enable only in a separate reviewed request.
                apply(child, args.properties)
                if child:IsA("BaseScript") then child.Disabled = true end
                child.Name = args.name
                child.Parent = node
            end)
            if not success then child:Destroy(); error(err) end
            return {name=child.Name, class=child.ClassName}
        elseif command.op == "set_properties" then
            assert(#command.path > 1, "Cannot change service properties")
            apply(node, args.properties)
        elseif command.op == "set_script" then
            assert(node:IsA("LuaSourceContainer"), "Target is not a script")
            assert(type(args.source) == "string", "source required")
            assert(type(args.expected_source) == "string", "expected_source required; inspect first")
            Scripts:UpdateSourceAsync(node, function(old)
                assert(old == args.expected_source, "Source changed; inspect and submit again")
                return args.source
            end)
        elseif command.op == "delete" then
            assert(#command.path > 1, "Cannot delete services")
            node:Destroy()
        else error("Unknown operation") end
        return {message="Applied"}
    end)
    -- A failed multi-property edit can be partial; commit lets the user undo it.
    History:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
    if not ok then error(tostring(result) .. " (may be partial; use Undo and inspect)") end
    return result
end
local function request(path, data)
    local response = Http:RequestAsync({Url=endpoint .. path, Method="POST", Headers={Authorization="Bearer " .. token, ["Content-Type"]="application/json"}, Body=Http:JSONEncode(data)})
    assert(response.Success, "HTTP " .. response.StatusCode .. ": " .. response.Body)
    return Http:JSONDecode(response.Body)
end
local function finish(accepted)
    if not pending or busy then return end
    busy = true
    local command = pending
    pending = nil
    if accepted then
        local ok, result = pcall(execute, command)
        outbox = {id=command.id, session=session, status=ok and "succeeded" or "failed", result=ok and result or {error=tostring(result)}}
    else
        outbox = {id=command.id, session=session, status="rejected", result={message="Rejected in Studio"}}
    end
    review.Text = Http:JSONEncode(outbox)
    busy = false
end
approve.MouseButton1Click:Connect(function() finish(true) end)
reject.MouseButton1Click:Connect(function() finish(false) end)
toggle.Click:Connect(function() widget.Enabled = not widget.Enabled end)
connect.MouseButton1Click:Connect(function()
    if connected then connected=false; status.Text="Disconnected"; return end
    local url = urlBox.Text:gsub("/+$", "")
    if not url:match("^https://") and not url:match("^http://127%.0%.0%.1:") and not url:match("^http://localhost:") then
        status.Text="Use HTTPS, or HTTP on localhost only"; return
    end
    if endpoint and (pending or outbox) and (url ~= endpoint or tokenBox.Text ~= token) then
        status.Text="Finish pending request/result before changing connection"; return
    end
    endpoint, token = url, tokenBox.Text
    connected=true
    status.Text="Connecting; allow the plugin's HTTP permission prompt."
end)
task.spawn(function()
    while true do
        task.wait(2)
        if connected and not busy then
            local ok, err = pcall(function()
                if outbox then
                    request("/v1/commands/" .. outbox.id, outbox)
                    outbox=nil
                end
                -- Heartbeat even while a request awaits approval.
                local response = request("/v1/poll", {session=session})
                if response.command then
                    assert(not pending, "Unexpected extra command")
                    pending=response.command
                    review.Text=Http:JSONEncode(pending)
                end
                status.Text=pending and "Review the full request. Approve or Reject." or "Connected • waiting for requests"
            end)
            if not ok then status.Text=tostring(err) end
        end
    end
end)
plugin.Unloading:Connect(function() connected=false end)
