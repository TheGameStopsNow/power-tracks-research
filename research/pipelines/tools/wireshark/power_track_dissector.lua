-- Power Track Frame Dissector for Wireshark
-- Detects and parses Power Track frames from captured tick data

-- Protocol name and description
local power_track_proto = Proto("PowerTrack", "Power Track Frame Protocol")

-- Field definitions
local f_opcode = ProtoField.uint8("powertrack.opcode", "Opcode", base.HEX, nil, 0xFC)
local f_version = ProtoField.uint8("powertrack.version", "Version", base.DEC, nil, 0x03)
local f_start_time = ProtoField.uint16("powertrack.start_time", "Start Time (us)", base.DEC)
local f_duration_scale = ProtoField.uint8("powertrack.duration_scale", "Duration Scale", base.DEC, nil, 0xFC)
local f_compression_ratio = ProtoField.uint8("powertrack.compression_ratio", "Compression Ratio", base.DEC, nil, 0x03)
local f_anchor_price = ProtoField.uint8("powertrack.anchor_price", "Anchor Price (cents)", base.DEC)
local f_volume_code = ProtoField.uint8("powertrack.volume_code", "Volume Code", base.DEC, nil, 0xFC)
local f_parity = ProtoField.uint8("powertrack.parity", "Parity", base.HEX, nil, 0x03)
local f_crc7 = ProtoField.uint8("powertrack.crc7", "CRC-7", base.HEX, nil, 0xFE)
local f_stop_bit = ProtoField.uint8("powertrack.stop_bit", "Stop Bit", base.DEC, nil, 0x01)
local f_payload = ProtoField.bytes("powertrack.payload", "Payload")
local f_xor_mask = ProtoField.uint8("powertrack.xor_mask", "XOR Mask", base.HEX)

power_track_proto.fields = {
    f_opcode,
    f_version,
    f_start_time,
    f_duration_scale,
    f_compression_ratio,
    f_anchor_price,
    f_volume_code,
    f_parity,
    f_crc7,
    f_stop_bit,
    f_payload,
    f_xor_mask
}

-- CRC-7 calculation function
local function crc7(data, polynomial)
    polynomial = polynomial or 0x09
    local crc = 0
    for i = 1, #data do
        crc = crc ~ data[i]
        for j = 1, 8 do
            if (crc & 0x80) ~= 0 then
                crc = ((crc << 1) ~ polynomial) & 0xFF
            else
                crc = (crc << 1) & 0xFF
            end
        end
    end
    return crc & 0x7F
end

-- XOR mask application
local function apply_xor_mask(data, mask)
    local result = {}
    for i = 1, #data do
        result[i] = data[i] ~ mask
    end
    return result
end

-- Frame validation
local function validate_frame(buffer, offset, mask)
    if buffer:len() - offset < 7 then
        return false, nil
    end
    
    -- Extract frame bytes
    local frame_bytes = {}
    for i = 0, 6 do
        frame_bytes[i + 1] = buffer(offset + i, 1):uint()
    end
    
    -- Apply XOR mask
    local unmasked = apply_xor_mask(frame_bytes, mask)
    
    -- Extract header (bytes 0-5)
    local header = {}
    for i = 1, 6 do
        header[i] = unmasked[i]
    end
    
    -- Compute CRC-7
    local computed_crc = crc7(header)
    
    -- Extract expected CRC from trailer (byte 6, bits 7-1)
    local trailer_byte = unmasked[7]
    local expected_crc = (trailer_byte >> 1) & 0x7F
    
    -- Check CRC
    local crc_valid = (computed_crc == expected_crc)
    
    -- Check stop bit
    local stop_bit = trailer_byte & 0x01
    local stop_bit_valid = (stop_bit == 1)
    
    return crc_valid and stop_bit_valid, unmasked
end

-- Dissector function
function power_track_proto.dissector(buffer, pinfo, tree)
    pinfo.cols.protocol = "PowerTrack"
    
    local offset = 0
    local frame_count = 0
    
    -- Try to discover XOR mask by testing common values
    local best_mask = nil
    local best_score = 0
    
    for mask = 0x00, 0x1F do
        local score = 0
        local test_offset = 0
        local valid_frames = 0
        
        -- Test first few frames with this mask
        for i = 1, math.min(10, math.floor((buffer:len() - test_offset) / 7)) do
            local valid, _ = validate_frame(buffer, test_offset, mask)
            if valid then
                valid_frames = valid_frames + 1
            end
            test_offset = test_offset + 7
        end
        
        if valid_frames > best_score then
            best_score = valid_frames
            best_mask = mask
        end
    end
    
    -- Use discovered mask or default to 0x00
    local mask = best_mask or 0x00
    
    -- Create protocol tree
    local subtree = tree:add(power_track_proto, buffer(), "Power Track Frames")
    subtree:add(f_xor_mask, mask)
    
    -- Parse frames
    while offset + 7 <= buffer:len() do
        local valid, unmasked = validate_frame(buffer, offset, mask)
        
        if valid then
            frame_count = frame_count + 1
            
            local frame_tree = subtree:add(power_track_proto, buffer(offset, 7), 
                string.format("Frame %d", frame_count))
            
            -- Parse header fields
            local byte0 = unmasked[1]
            frame_tree:add(f_opcode, byte0, (byte0 >> 2) & 0x3F)
            frame_tree:add(f_version, byte0, byte0 & 0x03)
            
            local start_time_lsb = unmasked[2]
            local start_time_msb = unmasked[3]
            local start_time = start_time_lsb | (start_time_msb << 8)
            frame_tree:add(f_start_time, start_time)
            
            local byte3 = unmasked[4]
            frame_tree:add(f_duration_scale, byte3, (byte3 >> 2) & 0x3F)
            frame_tree:add(f_compression_ratio, byte3, byte3 & 0x03)
            
            frame_tree:add(f_anchor_price, unmasked[5])
            
            local byte5 = unmasked[6]
            frame_tree:add(f_volume_code, byte5, (byte5 >> 2) & 0x3F)
            frame_tree:add(f_parity, byte5, byte5 & 0x03)
            
            local trailer_byte = unmasked[7]
            frame_tree:add(f_crc7, trailer_byte, (trailer_byte >> 1) & 0x7F)
            frame_tree:add(f_stop_bit, trailer_byte, trailer_byte & 0x01)
            
            -- Add payload if present
            if buffer:len() - offset > 7 then
                local payload_len = buffer:len() - offset - 7
                frame_tree:add(f_payload, buffer(offset + 7, payload_len))
            end
            
            offset = offset + 7
        else
            -- Try next byte if frame doesn't validate
            offset = offset + 1
            if offset >= buffer:len() then
                break
            end
        end
    end
    
    pinfo.cols.info = string.format("Power Track: %d frames (mask: 0x%02X)", frame_count, mask)
end

-- Register dissector for TCP port (adjust as needed)
-- local tcp_port = DissectorTable.get("tcp.port")
-- tcp_port:add(12345, power_track_proto)

-- Register as UDP dissector (adjust as needed)
-- local udp_port = DissectorTable.get("udp.port")
-- udp_port:add(12345, power_track_proto)

-- Register as a post-dissector to run after all other dissectors
register_postdissector(power_track_proto)


