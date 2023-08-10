# Open the font file
font = fontforge.open("myfont.ttf")

# Define the source (Arabic) and target (Chinese) Unicode code point ranges
source_start = 0x0600  # Unicode for first Arabic glyph
target_start = 0x6E00  # Unicode for U+6E00

# Copy glyphs within the specified range
num_glyphs_to_copy = 11172  # Number of Arabic glyphs
for offset in range(num_glyphs_to_copy):
    source_unicode = source_start + offset
    target_unicode = target_start + offset

    # Access the source and target glyphs
    source_glyph = font[chr(source_unicode)]
    target_glyph = font.createMappedChar(target_unicode)

    # Copy the outline from the source glyph to the target glyph
    target_glyph.clear()
    target_glyph.importOutlines(source_glyph)

# Save the modified font
font.save("modified_font.ttf")

# Close the font
font.close()