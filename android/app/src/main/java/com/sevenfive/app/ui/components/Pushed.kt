package com.sevenfive.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.sevenfive.app.ui.theme.AuroraBackground
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable

/** The round glass back button pushed screens share. */
@Composable
fun BackButton(onBack: () -> Unit) {
    Box(
        Modifier
            .padding(start = 8.dp)
            .size(38.dp)
            .pressable(onClick = onBack)
            .glassSurface(shape = CircleShape, strong = true),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            Icons.AutoMirrored.Outlined.ArrowBack,
            contentDescription = "Back",
            tint = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.size(20.dp),
        )
    }
}

/** A compact bar for screens that hold a web page: title, a quiet subtitle, glass back button. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PushTopBar(
    title: String,
    subtitle: String?,
    onBack: () -> Unit,
    actions: @Composable RowScope.() -> Unit = {},
) {
    TopAppBar(
        title = {
            Column {
                Text(title, style = MaterialTheme.typography.titleMedium)
                if (!subtitle.isNullOrBlank()) {
                    Text(
                        subtitle,
                        style = MaterialTheme.typography.labelMedium,
                        color = LocalAppColors.current.secondaryLabel,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        },
        navigationIcon = { BackButton(onBack) },
        actions = actions,
        colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent, scrolledContainerColor = Color.Transparent),
    )
}

/**
 * A pushed screen with a large title that collapses into a frosted bar, over the same backdrop as
 * the tabs. [content] gets padding for its scrolling column (top bar above, gesture bar below).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PushScaffold(title: String, onBack: () -> Unit, content: @Composable (PaddingValues) -> Unit) {
    val scroll = TopAppBarDefaults.pinnedScrollBehavior()
    val app = LocalAppColors.current
    // Above the tab bar where it shows, else above the system's navigation bar.
    val bottom = maxOf(
        WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding(),
        com.sevenfive.app.ui.theme.LocalBottomInset.current,
    )
    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        containerColor = MaterialTheme.colorScheme.background,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            // Solid once content slides under it; clear at the top. No blur: nothing to re-process.
            val barColor = MaterialTheme.colorScheme.background
            Column(Modifier.drawBehind { drawRect(barColor.copy(alpha = scroll.state.overlappedFraction)) }) {
                TopAppBar(
                    title = { Text(title, style = MaterialTheme.typography.headlineSmall, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    navigationIcon = { BackButton(onBack) },
                    scrollBehavior = scroll,
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = Color.Transparent,
                        scrolledContainerColor = Color.Transparent,
                    ),
                )
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(0.6.dp)
                        .graphicsLayer { alpha = scroll.state.overlappedFraction }
                        .background(app.hairline),
                )
            }
        },
    ) { inner ->
        Box(Modifier.fillMaxSize()) {
            AuroraBackground()
            content(
                PaddingValues(
                    start = 16.dp,
                    end = 16.dp,
                    top = inner.calculateTopPadding() + 4.dp,
                    bottom = bottom + 32.dp,
                ),
            )
        }
    }
}

/** An iOS inset-grouped section: a small header, a glass card of rows, an optional footnote. */
@Composable
fun Group(header: String? = null, footer: String? = null, content: @Composable ColumnScope.() -> Unit) {
    Column {
        if (header != null) SectionHeader(header, Modifier.padding(bottom = 4.dp))
        Column(Modifier.fillMaxWidth().glassSurface(shape = MaterialTheme.shapes.large), content = content)
        if (footer != null) {
            Text(
                footer,
                style = MaterialTheme.typography.bodySmall,
                color = LocalAppColors.current.secondaryLabel,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 6.dp),
            )
        }
    }
}

/** The hairline between rows of a group, inset past the icon like iOS. */
@Composable
fun GroupDivider(inset: Boolean = true) {
    Box(
        Modifier
            .padding(start = if (inset) 58.dp else 16.dp)
            .fillMaxWidth()
            .height(0.6.dp)
            .background(LocalAppColors.current.hairline),
    )
}

/** A row in a group: colour tile, title, optional detail, a chevron if it goes somewhere. */
@Composable
fun GroupRow(
    title: String,
    icon: ImageVector? = null,
    iconColor: Color = MaterialTheme.colorScheme.primary,
    detail: String? = null,
    titleColor: Color = Color.Unspecified,
    enabled: Boolean = true,
    busy: Boolean = false,
    chevron: Boolean = false,
    onClick: (() -> Unit)? = null,
) {
    val app = LocalAppColors.current
    Row(
        Modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.pressable(enabled = enabled && !busy, scaleTo = 0.985f, onClick = onClick) else Modifier)
            .padding(horizontal = 14.dp, vertical = 11.dp)
            .alpha(if (enabled) 1f else 0.45f),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            IconTile(icon, iconColor, size = 30.dp)
            Spacer(Modifier.width(14.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(
                title,
                style = MaterialTheme.typography.bodyLarge,
                color = if (titleColor == Color.Unspecified) MaterialTheme.colorScheme.onSurface else titleColor,
            )
            if (detail != null) {
                Text(detail, style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }
        }
        if (busy) {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.primary)
        } else if (chevron) {
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null, tint = app.tertiaryLabel)
        }
    }
}

/** A text field that sits inside a group: no box of its own, a quiet label above the value. */
@Composable
fun GroupField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    placeholder: String? = null,
    keyboardType: KeyboardType = KeyboardType.Uri,
) {
    TextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        placeholder = placeholder?.let { { Text(it) } },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        textStyle = MaterialTheme.typography.bodyLarge,
        colors = TextFieldDefaults.colors(
            focusedContainerColor = Color.Transparent,
            unfocusedContainerColor = Color.Transparent,
            disabledContainerColor = Color.Transparent,
            focusedIndicatorColor = Color.Transparent,
            unfocusedIndicatorColor = Color.Transparent,
            focusedLabelColor = MaterialTheme.colorScheme.primary,
            unfocusedLabelColor = LocalAppColors.current.secondaryLabel,
            cursorColor = MaterialTheme.colorScheme.primary,
        ),
        modifier = Modifier.fillMaxWidth(),
    )
}

/** A centred action in a group, like iOS's tinted text buttons. */
@Composable
fun GroupAction(
    text: String,
    onClick: () -> Unit,
    color: Color = MaterialTheme.colorScheme.primary,
    enabled: Boolean = true,
) {
    Text(
        text,
        style = MaterialTheme.typography.bodyLarge,
        fontWeight = FontWeight.SemiBold,
        color = color,
        textAlign = TextAlign.Center,
        modifier = Modifier
            .fillMaxWidth()
            .pressable(enabled = enabled, scaleTo = 0.985f, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 13.dp)
            .alpha(if (enabled) 1f else 0.4f),
    )
}

/** A row with a switch: colour tile, title, optional detail, the switch at the end. */
@Composable
fun GroupSwitchRow(
    title: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
    icon: ImageVector? = null,
    iconColor: Color = MaterialTheme.colorScheme.primary,
    detail: String? = null,
    enabled: Boolean = true,
) {
    val app = LocalAppColors.current
    Row(
        Modifier
            .fillMaxWidth()
            .pressable(enabled = enabled, scaleTo = 0.985f) { onChange(!checked) }
            .padding(horizontal = 14.dp, vertical = 9.dp)
            .alpha(if (enabled) 1f else 0.45f),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            IconTile(icon, iconColor, size = 30.dp)
            Spacer(Modifier.width(14.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            if (detail != null) {
                Text(detail, style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
            }
        }
        Spacer(Modifier.width(10.dp))
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            enabled = enabled,
            colors = SwitchDefaults.colors(checkedTrackColor = MaterialTheme.colorScheme.primary),
        )
    }
}
