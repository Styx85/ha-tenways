# Automations and dashboards

Examples that run in Home Assistant with this integration. Since 0.13.0 the integration's options *Clear the trip once a day* and *Set the clock automatically* do the first two in the poll's own connection, which also works when you ride off right after switching on; the automations need a second connection a few seconds later. Adjust the entity IDs to yours under Settings → Entities. Back to the [README](../README.md).

## Example: set the clock automatically

The bike is only reachable while it is switched on, so a fixed time does not work. This automation runs after each successful read instead and presses **Set clock** when the clock was last set before a daylight saving change, or more than 90 days ago. The time of the last *successful* press is kept in a helper, because the button records every press, failed ones included; a failed press is tried again on a later read, at most once an hour. Running in Home Assistant since November 2026.

Helper (`configuration.yaml`, or create a Date and time helper in the UI):

```yaml
input_datetime:
  tenways_clock_last_set:
    name: TENWAYS clock last set
    has_date: true
    has_time: true
```

Automation (adjust the entity IDs to yours under Settings → Entities):

```yaml
- id: tenways_set_clock
  alias: TENWAYS set clock (time change / every 90 days)
  triggers:
    - trigger: state
      entity_id: sensor.longtail_duo_last_successful_read
      # ignore reloads, where the restored value comes back from unavailable
      not_from: [unavailable, unknown]
      not_to: [unavailable, unknown]
  conditions:
    # at most one attempt an hour if setting the clock keeps failing
    - condition: template
      value_template: >-
        {{ this.attributes.last_triggered is none
           or now() - this.attributes.last_triggered > timedelta(hours=1) }}
    - condition: template
      value_template: >-
        {% set ts = state_attr('input_datetime.tenways_clock_last_set', 'timestamp') %}
        {% if ts is none %}true{% else %}
        {% set last = as_local(as_datetime(ts)) %}
        {{ last.utcoffset() != now().utcoffset() or now() - last > timedelta(days=90) }}
        {% endif %}
  actions:
    - delay: "00:00:05"
    # raises an error if the bike does not acknowledge; then the steps below are skipped
    - action: button.press
      target:
        entity_id: button.longtail_duo_set_clock
    - action: input_datetime.set_datetime
      target:
        entity_id: input_datetime.tenways_clock_last_set
      data:
        timestamp: "{{ now().timestamp() }}"
  mode: single
  max_exceeded: silent
```

A new helper starts at 1970, so the first read after setting this up sets the clock once.

## Example: a fresh trip every day

Clears the trip after the first successful read of each day, so the display shows today's ride. Yesterday's trip distance, ride time, average and maximum speed are lost on the bike; HA keeps their history and its [totals](entities.md#totals-over-all-trips-and-per-day) keep counting. As with the clock example, the time of the last *successful* reset is kept in a helper, because the button records failed presses too; a failed press is tried again on a later read, at most once an hour.

```yaml
input_datetime:
  tenways_trip_last_reset:
    name: TENWAYS trip last reset
    has_date: true
    has_time: true
```

```yaml
- id: tenways_daily_trip_reset
  alias: TENWAYS reset trip once a day
  triggers:
    - trigger: state
      entity_id: sensor.longtail_duo_last_successful_read
      not_from: [unavailable, unknown]
      not_to: [unavailable, unknown]
  conditions:
    - condition: template
      value_template: >-
        {{ this.attributes.last_triggered is none
           or now() - this.attributes.last_triggered > timedelta(hours=1) }}
    - condition: template
      value_template: >-
        {% set ts = state_attr('input_datetime.tenways_trip_last_reset', 'timestamp') %}
        {{ ts is none or as_local(as_datetime(ts)).date() < now().date() }}
  actions:
    - delay: "00:00:05"
    # raises an error if the bike does not acknowledge; then the step below is skipped
    - action: button.press
      target:
        entity_id: button.longtail_duo_reset_trip
    - action: input_datetime.set_datetime
      target:
        entity_id: input_datetime.tenways_trip_last_reset
      data:
        timestamp: "{{ now().timestamp() }}"
  mode: single
  max_exceeded: silent
```

## Distance per period and ride log

The **Odometer** is a `total_increasing` sensor, so Home Assistant keeps long-term statistics for it. A statistics graph shows the distance per day, week or month:

```yaml
type: statistics-graph
entities: [sensor.longtail_duo_odometer]
stat_types: [change]
period: week
chart_type: bar
```

Adjust the entity ID to yours. HA only sees the bike while it is in Bluetooth range, so a ride is counted when the bike is next seen at home, not while it is out.

For a **ride log in a calendar** (start, end, distance, duration, average speed, battery use) there is a ready-made blueprint in [stein155/tenways-bridge](https://github.com/stein155/tenways-bridge/blob/main/homeassistant/blueprints/automation/tenways_rides.yaml) (MIT). It works from the odometer and takes its inputs as entity selectors by device class, not by name. Pick this integration's **Odometer**, **Ride duration** and **Traction battery** sensors, a calendar (a local calendar works) and a text helper. We have not tried it with this integration yet; please report how it goes.
